import threading
from PyQt4.QtCore import QIODevice, QFile, QFileInfo, QBuffer
import hex.settings as settings
import hex.utils as utils


globalSettings = settings.globalSettings()


class OutOfBoundsError(IOError):
    pass


class AbstractDevice(object):
    def __init__(self, name=''):
        self.lock = threading.RLock()
        self.name = name
        self._cache = bytes()
        self._cacheStart = 0
        self._cacheSize = 1024 * 1024
        self._cacheBoundary = 1024

    def _read(self, position, length):
        raise NotImplementedError()

    @property
    def fixedSize(self):
        raise NotImplementedError()

    @property
    def readOnly(self):
        raise NotImplementedError()

    def read(self, position, length):
        with self.lock:
            if length < 0:
                raise OutOfBoundsError()
            elif length == 0:
                return bytes()

            if self._cacheStart <= position < self._cacheStart + len(self._cache):
                # how many bytes we can read from cache?
                cached_length = min(length, self._cacheStart + len(self._cache) - position)
                cache_offset = position - self._cacheStart
                # read cached data into first part
                first_part = self._cache[cache_offset:cache_offset + cached_length]
                if cached_length < length:
                    # also read data that is out of cache
                    return first_part + self._read(position + cached_length, length - cached_length)
                else:
                    return first_part
            elif self._cacheSize > 0:
                # cache miss - we should move cache
                # it is best to choose position to force current pos to be in center of cache
                ideal_start = max(0, position - self._cacheSize // 2)
                ideal_start = ideal_start - ideal_start % self._cacheBoundary
                if ideal_start + self._cacheSize <= position:
                    ideal_start = position - position % self._cacheBoundary

                new_cache = self._read(ideal_start, self._cacheSize)
                self._cacheStart = ideal_start
                self._cache = new_cache

                # and try to read again...
                return self.read(position, length)
            else:
                return self._read(position, length)


class QtProxyDevice(AbstractDevice):
    def __init__(self, qdevice, name):
        AbstractDevice.__init__(self, name)
        self._qdevice = qdevice
        self._deviceSize = qdevice.size() if qdevice is not None else 0
        self._pos = 0

    def __len__(self):
        return self._deviceSize

    def _read(self, position, length):
        if self._pos != position:
            if not self._qdevice.seek(position):
                raise IOError(utils.tr('failed to seek to position {0}').format(position))
            else:
                self._pos = position

        return self._qdevice.read(length)

    @property
    def readOnly(self):
        return not self._qdevice.openMode() & QIODevice.ReadOnly or not self._qdevice.openMode() & QIODevice.WriteOnly


class FileDevice(QtProxyDevice):
    def __init__(self, filename, read_only=False, memory_load=False, freeze_size=False):
        file_info = QFileInfo(filename)
        if not file_info.exists():
            raise IOError(utils.tr('file {0} does not exist'))
        if memory_load and file_info.size() > globalSettings['files.max_memoryload_size']:
            raise IOError(utils.tr('cannot load file into memory that has size {0}')
                                    .format(utils.formatSize(file_info.size())))

        qdevice = QFile(filename)
        if not qdevice.open(QFile.ReadOnly if read_only else QFile.ReadWrite):
            raise IOError('failed to open file {0}'.format(filename))
        QtProxyDevice.__init__(self, qdevice, filename)

        if memory_load:
            self._cacheSize = file_info.size()

        self._fixedSize = freeze_size

    @property
    def fixedSize(self):
        return self._fixedSize


class BufferDevice(QtProxyDevice):
    def __init__(self, arr, read_only=False, freeze_size=False, name=''):
        self.arr = arr # to keep QByteArray safe from Python GC...
        device = QBuffer(arr)
        if not device.open(QBuffer.ReadOnly if read_only else QBuffer.ReadWrite):
            raise IOError('failed to open device')
        QtProxyDevice.__init__(self, device, name)
        self._fixedSize = freeze_size

    @property
    def fixedSize(self):
        return self._fixedSize


class RangeProxyDevice(AbstractDevice):
    def __init__(self, device, range_start, range_length, memory_load=False, name=''):
        AbstractDevice.__init__(self, name)
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
