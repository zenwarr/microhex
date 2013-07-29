import random
import weakref
import os
from PyQt4.QtCore import QIODevice, QFile, QFileInfo, QBuffer, QUrl, QByteArray, QObject, pyqtSignal
import hex.settings as settings
import hex.appsettings as appsettings
import hex.utils as utils


globalSettings = settings.globalSettings()
MaxMemoryLoadSize = globalSettings[appsettings.Files_MaxMemoryLoadSize]
MaximalWriteBlock = 1024 * 1024 * 64  # 64 MB


_devices = weakref.WeakValueDictionary()


class OutOfBoundsError(IOError):
    pass


class AbstractDevice(QObject):
    urlChanged = pyqtSignal(object)

    def __init__(self, url=None, options=None):
        QObject.__init__(self)
        self._url = QUrl(url)
        self._cache = bytes()
        self._cacheStart = 0
        self._cacheLength = 0
        self._cacheSize = 4
        self._cacheBoundary = 2
        self.options = options
        self._spans = weakref.WeakSet()

    def _read(self, position, length):
        raise NotImplementedError()

    @property
    def fixedSize(self):
        raise NotImplementedError()

    @property
    def length(self):
        raise NotImplementedError()

    @property
    def readOnly(self):
        if hasattr(self.options, 'readOnly'):
            return self.options.readOnly
        raise NotImplementedError()

    def read(self, position, length):
        if position < 0 or length < 0:
            raise OutOfBoundsError()
        elif not length:
            return bytes()

        cache_start = self._cacheStart
        cache_end = cache_start + self._cacheLength
        if cache_start <= position < cache_end:
            cache_offset = position - cache_start
            if length <= cache_end - position:
                return self._cache[cache_offset:cache_offset + length]
            else:
                return self._cache[cache_offset:cache_end] + self._read(cache_end, length - (cache_end - position))
        elif self._cacheSize > 0:
            # cache miss - we should move cache
            self._encache(position, center=True)
            return self.read(position, length)
        else:
            return self._read(position, length)

    def byteRange(self, position, length):
        if position < 0 or length < 0:
            raise OutOfBoundsError()

        if self._cacheSize > 0:
            current_position = position
            while current_position < position + length:
                cache_start = self._cacheStart
                cache_end = cache_start + self._cacheLength
                cache = self._cache
                if cache_start <= current_position < cache_end:
                    cached_bytes_count = min(length, cache_end - current_position)
                    cache_offset = current_position - self._cacheStart
                    yield from cache[cache_offset:cache_offset + cached_bytes_count]
                    current_position += cached_bytes_count
                else:
                    self._encache(current_position, center=(length - (current_position - position) < self._cacheSize))
        else:
            for byte_index in range(position, position + length):
                yield self._read(byte_index, 1)

    def _encache(self, from_position, center):
        assert self._cacheBoundary <= self._cacheSize
        if center:
            cache_start = max(0, from_position - self._cacheSize // 2)
            cache_start -= cache_start % self._cacheBoundary
            if cache_start + self._cacheSize <= from_position:
                cache_start = from_position - from_position % self._cacheBoundary
        else:
            cache_start = from_position - from_position % self._cacheBoundary

        new_cache = self._read(cache_start, self._cacheSize)
        self._cacheStart = cache_start
        self._cache = new_cache
        self._cacheLength = len(self._cache)

    def _write(self, position, data):
        raise NotImplementedError()

    def write(self, position, data):
        """Writes data at :position:, overwriting existing data. Returns number of bytes actually written.
        """
        bytes_written = self._write(position, data)
        # if data is written into cache frame, drop cache
        if utils.checkRangesIntersect(position, len(data), self._cacheStart, len(self._cache)):
            self._cache = b''
            self._cacheLength = 0
        return bytes_written

    def createSaver(self, editor, read_device):
        """Create saver to save data from :read_device: to this device."""
        if not editor.checkCanQuickSave() and read_device is self:
            raise IOError('it is impossible to save this editor data to same device')
        return StandardSaver(read_device, self)

    @property
    def url(self):
        return self._url

    def _addSpan(self, device_span):
        self._spans.add(device_span)

    def _removeSpan(self, device_span):
        self._spans.remove(device_span)


class NullDevice(AbstractDevice):
    def __init__(self):
        AbstractDevice.__init__(self, 'microhex:null')

    def __len__(self):
        return 0

    def _read(self, position, length):
        return b''

    @property
    def fixedSize(self):
        return False

    @property
    def readOnly(self):
        return False

    def _write(self, position, data):
        return len(data)


class StandardSaver(object):
    def __init__(self, read_device, write_device):
        self.readDevice = read_device
        self.writeDevice = write_device
        self.position = 0

    def begin(self):
        if hasattr(self.writeDevice, 'clear'):
            self.writeDevice.clear()

    def putSpan(self, span):
        span_offset = 0
        while span_offset < len(span):
            read_length = min(len(span) - span_offset, MaximalWriteBlock)
            span_data = span.read(span_offset, read_length)
            if self.writeDevice.write(self.position, span_data) != read_length:
                raise IOError(utils.tr('failed to write {0}: not all data was written').format(
                            utils.formatSize(self.writeDevice.url.toString())))
            self.position += read_length
            span_offset += read_length

    def fail(self):
        # what can i do? i'm just a little python object in this cruel world...
        pass

    def complete(self):
        # yeah, we did it!
        pass


class QtProxyDevice(AbstractDevice):
    def __init__(self, qdevice, url=None, options=None):
        AbstractDevice.__init__(self, url, options)
        self._qdevice = qdevice
        self._deviceOpened = qdevice.isOpen()
        self._size = qdevice.size() if self._deviceOpened else 0
        qdevice.aboutToClose.connect(self._onDeviceAboutToClose)

    def _onDeviceAboutToClose(self):
        self._deviceOpened = False

    def _ensureOpened(self):
        if not self._deviceOpened:
            if not self._qdevice.open(QIODevice.ReadOnly if self.options.readOnly else QIODevice.ReadWrite):
                raise IOError(self._qdevice.errorString())
            self._deviceOpened = True
            self._size = self._qdevice.size()

    @property
    def length(self):
        self._ensureOpened()
        return self._size

    def __len__(self):
        return self.length

    def _read(self, position, length):
        self._ensureOpened()
        if not self._qdevice.seek(position):
            raise IOError(utils.tr('failed to seek to position {0} ({1})').format(position, self._qdevice.errorString()))
        return self._qdevice.read(length)

    @property
    def readOnly(self):
        if self._qdevice is None:
            return True
        if self._qdevice.isOpen():
            return not self._qdevice.openMode() & QIODevice.ReadOnly or not self._qdevice.openMode() & QIODevice.WriteOnly
        else:
            return self.options.readOnly

    @property
    def qdevice(self):
        return self._qdevice

    def _write(self, position, data):
        self._ensureOpened()
        self._qdevice.seek(position)
        bytes_written = self._qdevice.write(data)
        if bytes_written < 0:
            raise IOError(self._qdevice.errorString())
        self._size = self._qdevice.size()
        return bytes_written


class FileDevice(QtProxyDevice):
    def __init__(self, file, options=None):
        options = options or FileLoadOptions()

        if isinstance(file, QFile):
            qdevice = file
            url = QUrl.fromLocalFile(file.fileName())
            file_info = QFileInfo(file)
        else:
            filename = file.toLocalFile() if isinstance(file, QUrl) else file

            file_info = QFileInfo(filename)
            if not options.forceNew and not file_info.exists():
                raise IOError(utils.tr('file {0} does not exist').format(filename))
            if options.memoryLoad and file_info.size() > globalSettings[appsettings.Files_MaxMemoryLoadSize]:
                raise IOError(utils.tr('cannot load file into memory that has size {0}')
                                        .format(utils.formatSize(file_info.size())))

            qdevice = QFile(filename)
            url = QUrl.fromLocalFile(filename)

        QtProxyDevice.__init__(self, qdevice, url, options)

        if options.memoryLoad:
            self._cacheSize = file_info.size()

        self._fixedSize = options.freezeSize

    @property
    def fixedSize(self):
        return self._fixedSize

    def clear(self):
        self._qdevice.resize(0)

    def resize(self, new_size):
        self._ensureOpened()
        if not self._qdevice.resize(new_size):
            raise IOError(utils.tr('failed to resize file {0} to size {1}').format(self.url.toString(),
                                                                                   utils.formatSize(new_size)))

    def createSaver(self, editor, read_device):
        if editor.checkCanQuickSave():
            return QuickFileSaver(editor, read_device, self)
        else:
            return FileSaver(read_device, self)


class FileSaver(StandardSaver):
    def __init__(self, read_device, write_device):
        self.originalWriteDevice = write_device
        load_options = FileLoadOptions()
        load_options.forceNew = True
        StandardSaver.__init__(self, read_device, FileDevice(get_temp_filename(
                                            write_device.url.toLocalFile(), 'mhs'), load_options))

    def complete(self):
        # move temporary file into original one. We should close devices before it
        self.originalWriteDevice.qdevice.close()
        self.writeDevice.qdevice.close()

        # remove file we should move into
        if not self.originalWriteDevice.qdevice.remove():
            raise IOError(utils.tr('failed to remove {0}: {1}').format(self.originalWriteDevice.name,
                                                                       self.originalWriteDevice.qdevice.errorString()))

        # and move (rename)
        if not self.writeDevice.qdevice.rename(self.originalWriteDevice.url.toLocalFile()):
            raise IOError(utils.tr('failed to move {0} into {1}: {2}').format(self.writeDevice.name,
                                                                         self.originalWriteDevice.name,
                                                                         self.writeDevice.errorString()))


class QuickFileSaver(StandardSaver):
    def __init__(self, editor, read_device, write_device):
        self.editor = editor
        StandardSaver.__init__(self, read_device, write_device)

    def begin(self):
        # no need to clear device before saving, but resize file to editor' size
        self.writeDevice.resize(len(self.editor))

    def putSpan(self, span):
        from hex.editor import Span, DeviceSpan

        # skip spans that are native. We assume that no DeviceSpans from this device are moved.
        if isinstance(span, DeviceSpan) and span.device is self.writeDevice:
            self.position += len(span)
            return

        StandardSaver.putSpan(self, span)


class BufferDevice(QtProxyDevice):
    def __init__(self, arr, options=None):
        options = options or BufferLoadOptions()

        if isinstance(arr, QBuffer):
            device = arr
        else:
            if isinstance(arr, bytes):
                arr = QByteArray(bytes)
            self.arr = arr # to keep QByteArray safe from Python GC...
            device = QBuffer(arr)

        QtProxyDevice.__init__(self, device, QUrl('data://'), options)
        self._fixedSize = options.freezeSize

    @property
    def fixedSize(self):
        return self._fixedSize


class RangeProxyDevice(AbstractDevice):
    def __init__(self, device, range_start, range_length, options=None):
        AbstractDevice.__init__(self, device.url)
        self.device = device
        self.rangeStart = range_start
        self.rangeLength = range_length
        # turn caching off
        self._cacheSize = 0

    def _read(self, position, length):
        return self.device.read(position + self.rangeStart, length)

    def __len__(self):
        return self.rangeLength

    @property
    def fixedSize(self):
        return True

    @property
    def readOnly(self):
        return self.device.readOnly


def get_temp_filename(filename, suffix):
    backoff_filename = '{0}.{1}'.format(filename, suffix)
    while QFileInfo(backoff_filename).exists():
        random.seed()
        backoff_filename = '{0}.{1}-{2}'.format(filename, suffix, random.randint(1, 1000000))
    return backoff_filename


class FileLoadOptions(object):
    def __init__(self):
        self.range = None
        self.memoryLoad = False
        self.readOnly = False
        self.freezeSize = False
        self.forceNew = False


class BufferLoadOptions(object):
    def __init__(self):
        self.data = QByteArray()
        self.readOnly = False
        self.freezeSize = False
        self.range = None


def deviceFromUrl(url, options=None):
    if isinstance(url, str):
        url = QUrl(url)
    normalized_url_text = normalize_url(url).toString(QUrl.StripTrailingSlash)

    global _devices
    if normalized_url_text in _devices:
        return _devices[normalized_url_text] # well, actual device load options can greatly differ
                                             # from requested ones...

    reusable = False

    if url.isLocalFile():
        # this is file...
        options = options or FileLoadOptions()
        rdevice = FileDevice(url, options)
        reusable = True
    elif url.scheme() == 'data':
        options = options or BufferLoadOptions()
        rdevice = BufferDevice(options.data)
    else:
        raise IOError(utils.tr('unknown scheme for device URL: {0}').format(url.toString()))

    if options.range is not None:
        if options.range[1] > MaxMemoryLoadSize:
            raise IOError(utils.tr('failed to load {0} bytes into memory: limit is {1}').format(
                          utils.formatSize(options.range[1]), utils.formatSize(MaxMemoryLoadSize)))
        device = RangeProxyDevice(rdevice, options.range[0], options.range[1], options)
    else:
        device = rdevice

    if reusable:
        _devices[normalized_url_text] = device
    return device


def normalize_url(url):
    if url.isLocalFile():
        url = QUrl.fromLocalFile(os.path.normpath(url.toLocalFile()))
    url.setScheme(url.scheme().lower())
    return url


def deviceFromBytes(data, load_options=None):
    """Wrapper around deviceFromUrl"""
    load_options = load_options or BufferLoadOptions()
    load_options.data = data if isinstance(data, QByteArray) else QByteArray(data)
    return deviceFromUrl(QUrl('data://'), load_options)
