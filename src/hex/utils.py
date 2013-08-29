from PyQt4.QtCore import QCoreApplication, QByteArray, QSize, QObject, pyqtSignal
from PyQt4.QtGui import QDialog, QFontDatabase, QColor, QIcon, qApp
import os
import contextlib
import random
import re
import html
import threading
import copy


applicationPath = ''
guiThread = None
testRun = False

MaximalPosition = 0xffffffffffffffff - 1


def first(iterable, default=None):
    return next(iter(iterable), default)


def indexOf(iterable, condition, default=None):
    return first((index for index, value in enumerate(iterable) if condition(value)), default)


def keyFromValue(dct, condition, default=None):
    return first((key for key, value in dct.items() if condition(value)), default)


def deepCopyAttrs(obj_from, obj_to, names):
    for name in names:
        setattr(obj_to, name, copy.deepcopy(getattr(obj_from, name)))


def tr(text, context='utils', disambiguation=None):
    return QCoreApplication.translate(context, text, disambiguation, QCoreApplication.UnicodeUTF8)


def lastFileDialogPath():
    from hex.settings import globalQuickSettings

    qs = globalQuickSettings()
    last_dir = qs['last_filedialog_path']
    return last_dir if isinstance(last_dir, str) else ''


def setLastFileDialogPath(new_path):
    from hex.settings import globalQuickSettings

    qs = globalQuickSettings()
    if os.path.exists(new_path) and os.path.isfile(new_path):
        new_path = os.path.dirname(new_path)
    qs['last_filedialog_path'] = new_path


_q = (
    ('Tb', 1024 * 1024 * 1024 * 1024),
    ('Gb', 1024 * 1024 * 1024),
    ('Mb', 1024 * 1024),
    ('Kb', 1024)
)


def formatSize(size):
    for q in _q:
        if size >= q[1]:
            size = size / q[1]
            postfix = q[0]
            break
    else:
        postfix = 'b'

    num = str(round(size, 2))
    if num.endswith('.0'):
        num = num[:-2]
    return num + ' ' + postfix


class Dialog(QDialog):
    """Dialog that remembers position and size"""

    def __init__(self, parent=None, name=''):
        QDialog.__init__(self, parent)
        self.name = name
        self.loadGeometry()

    def loadGeometry(self):
        import hex.settings as settings

        if self.name:
            saved_geom = settings.globalQuickSettings()[self.name + '.geometry']
            if saved_geom and isinstance(saved_geom, str):
                self.restoreGeometry(QByteArray.fromHex(saved_geom))

    def accept(self):
        self.__save()
        QDialog.accept(self)

    def reject(self):
        self.__save()
        QDialog.reject(self)

    def __save(self):
        import hex.settings as settings

        if self.name:
            settings.globalQuickSettings()[self.name + '.geometry'] = str(self.saveGeometry().toHex(), encoding='ascii')


def camelCaseToUnderscore(camel_case):
    return ''.join(('_' + c.lower() if c.isupper() else c) for c in camel_case)


def underscoreToCamelCase(underscore):
    result = list()
    word_start = False
    for ch in underscore:
        if ch == '_':
            word_start = True
        else:
            result.append(ch.upper() if word_start else ch)
            word_start = False
    return ''.join(result)


def isFontInstalled(font_family):
    return font_family in QFontDatabase().families()


def checkRangesIntersect(start1, length1, start2, length2):
    if start2 < start1:
        t = start2
        start2 = start1
        start1 = t

        t = length2
        length2 = length1
        length1 = t

    return start2 - start1 < length1


@contextlib.contextmanager
def readlock(lock):
    lock.lockForRead()
    try:
        yield
    finally:
        lock.unlockRead()


@contextlib.contextmanager
def writelock(lock):
    lock.lockForWrite()
    try:
        yield
    finally:
        lock.unlockWrite()


def generateRandomColor():
    random.seed()
    return QColor(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))


def getIcon(icon_name):
    icon = QIcon.fromTheme(icon_name)
    if icon.isNull():
        icon = QIcon()
        icon.addFile(':/main/images/' + icon_name + '16.png', QSize(16, 16))
        icon.addFile(':/main/images/' + icon_name + '32.png', QSize(32, 32))
    return icon


def skip(iterable, count=1):
    for x in range(count):
        next(iterable)


def isNone(obj):
    return obj is None or (hasattr(obj, 'isNull') and obj.isNull())


def isClone(obj1, obj2):
    return obj1 is obj2 or (hasattr(obj1, 'isClone') and obj1.isClone(obj2)) or (hasattr(obj2, 'isClone') and obj2.isClone(obj1))


_blacklisted = re.compile(r'[\\/|\?\*<>":\+]')


def isValidFilename(filename):
    """Checks if given text is valid filename and does not contain any directory separators"""
    return re.search(_blacklisted, filename) is None


def htmlEscape(text):
    return html.escape(text).replace(' ', '&nbsp;')


def checkMask(value, mask):
    """Return False if there is at least one bit in :value: that is not set in :mask:
    """
    return bool(value | mask == mask)


class SignalConnector(object):
    def __init__(self, target=None, **kwargs):
        self._target = None
        self._connections = tuple(kwargs.items())
        self._switchTarget(target)

    @property
    def target(self):
        return self._target

    @target.setter
    def target(self, new_target):
        self._switchTarget(new_target)

    def _switchTarget(self, new_target):
        if new_target is not self._target:
            if self._target is not None:
                for conn_data in self._connections:
                    if hasattr(self._target, conn_data[0]):
                        getattr(self._target, conn_data[0]).disconnect(conn_data[1])

            self._target = new_target

            if new_target is not None:
                for conn_data in self._connections:
                    if hasattr(new_target, conn_data[0]):
                        getattr(new_target, conn_data[0]).connect(conn_data[1])


def buildGetter(attr_name):
    return property(lambda self: getattr(self, attr_name))

def buildGetters(*args):
    return (buildGetter(attr_name) for attr_name in args)


class DynamicBufferRange(QObject):
    moved = pyqtSignal(object, object)  # new_start_position, old_start_position
    resized = pyqtSignal(object, object)  # new_size, old_size
    updated = pyqtSignal()
    dataChanged = pyqtSignal()

    def __init__(self, start=0, length=0, fixed=True, allow_resize=False):
        QObject.__init__(self)
        self.lock = threading.RLock()
        self._start = start
        self._length = length
        self._fixed = fixed
        self._allowResize = allow_resize

        self.moved.connect(self.updated)
        self.resized.connect(self.updated)

    start, length, fixed, allowResize = buildGetters('_start', '_length', '_fixed', '_allowResize')

    @property
    def valid(self) -> bool:
        raise NotImplementedError()

    @property
    def startPosition(self) -> int:
        raise NotImplementedError()

    @property
    def size(self) -> int:
        raise NotImplementedError()

    @property
    def lastPosition(self):
        return self.startPosition + self.size - 1

    def _move(self, new_start):
        new_start = max(0, new_start)
        if new_start != self._start:
            old_start = self._start
            self._start = new_start
            self.moved.emit(new_start, old_start)

    def _resize(self, new_length):
        new_length = max(0, new_length)
        if self._allowResize and new_length != self._length:
            old_length = self._length
            self._length = new_length
            self.resized.emit(new_length, old_length)

    def _onInsert(self, start, length):
        with self.lock:
            if self.valid and not self.fixed:
                if start < self._start:
                    self._move(self._start + length)
                elif self.allowResize and self._start <= start and (start < self._start + self._length or
                                                                    self._length == 0 and start == self._start):
                    self._resize(self._length + length)

    def _onRemove(self, start, length):
        with self.lock:
            if self.valid and not self.fixed:
                if start < self._start:
                    if self._allowResize and start + length > self._start:
                        self._resize(max(0, self._length - start - length + self._start))
                    self._move(max(start, self._start - length))
                elif self._allowResize and self._start <= start < self._start + self._length:
                    self._resize(max(start - self._start, self._length - length))

    def _onDataChanged(self, start, length):
        with self.lock:
            if self.valid and checkRangesIntersect(self._start, self._length, start, length):
                self.dataChanged.emit()

    def __bool__(self):
        with self.lock:
            return self.valid and bool(self.size)

    def __eq__(self, other):
        if not isinstance(other, DynamicBufferRange):
            return NotImplemented
        return self.startPosition == other.startPosition and self.size == other.size

    def intersectsWith(self, other):
        return checkRangesIntersect(self.startPosition, self.size, other.startPosition, other.size)

    def contains(self, other):
        return other.startPosition >= self.startPosition and other.lastPosition <= self.lastPosition

    def clone(self, fixed=None, allow_resize=None):
        raise NotImplementedError()

    def createCursor(self, offset=0, length=-1):
        pass


class DocumentRange(DynamicBufferRange):
    def __init__(self, document, start, size, fixed=True, allow_resize=False):
        DynamicBufferRange.__init__(self, start, size, fixed, allow_resize)
        if not fixed:
            self._documentConnector = SignalConnector(document, bytesInserted=self._onInsert,
                                                      bytesRemoved=self._onRemove, dataChanged=self._onDataChanged)
        else:
            self._documentConnector = SignalConnector(document, dataChanged=self._onDataChanged)

    @property
    def document(self):
        return self._documentConnector.target

    @property
    def startPosition(self):
        with self.lock:
            return self._start if self.valid else -1

    @property
    def size(self):
        with self.lock:
            return self._length if self.valid else 0

    @property
    def valid(self):
        with self.lock:
            return self._documentConnector.target is not None and self._start >= 0 and self._length >= 0

    def clone(self, fixed=None, allow_resize=None):
        with self.lock:
            return DocumentRange(self.document, self.start, self.length, self.fixed if fixed is None else fixed,
                                 self.allowResize if allow_resize is None else allow_resize)

    def createCursor(self, offset=0, length=-1):
        if offset >= self.size:
            raise IndexError('offset is out of range')
        return DocumentCursor(self.startPosition + offset, override_buffer_length=length)


class IndexRange(DynamicBufferRange):
    def __init__(self, model, start, length, fixed=True, allow_resize=False):
        DynamicBufferRange.__init__(self, start.offset, length, fixed, allow_resize)
        self._invalidated = False
        if not fixed:
            self._modelConnector = SignalConnector(model, indexesInserted=self._onInsert,
                                                   indexesRemoved=self._onRemove, dataChanged=self._onDataChanged)
        else:
            self._modelConnector = SignalConnector(model, dataChanged=self._onDataChanged)

    @property
    def model(self):
        return self._modelConnector.target

    @property
    def startPosition(self):
        with self.lock:
            return self.model.indexFromOffset(self._start).documentPosition if self.valid else -1

    @property
    def size(self):
        return self.sizeOfIndexes(self._length)

    def sizeOfIndexes(self, index_count):
        with self.lock:
            if not self.valid:
                return 0
            first_index = self.model.indexFromOffset(self._start)
            if not first_index:
                return 0
            last_index = self.model.indexFromOffset(self._start + index_count - 1)
            if last_index:
                return last_index.documentPosition + last_index.dataSize - first_index.documentPosition
            else:
                return self.model.document.length - first_index.documentPosition

    @property
    def valid(self):
        with self.lock:
            return (self._modelConnector.target is not None and self._start >= 0 and self._length >= 0 and
                    not self._invalidated)

    def _onInsert(self, start, length):
        DynamicBufferRange._onInsert(self, start.offset, length)

    def _onRemove(self, start, length):
        DynamicBufferRange._onRemove(self, start.offset + 1 if start.valid else 0, length)

    def _onDataChanged(self, first, last):
        DynamicBufferRange._onDataChanged(self, first.offset, last - first)

    def clone(self, fixed=None, allow_resize=None):
        with self.lock:
            return IndexRange(self.model, self.start, self.length, self.fixed if fixed is None else fixed,
                              self.allowResize if allow_resize is None else allow_resize)

    def createCursor(self, offset=0, length=-1):
        if offset >= self.size:
            raise IndexError('offset is out of range')
        return DocumentCursor(self.startPosition + offset, self.sizeOfIndexes(length) if length >= 0 else -1)


class DataRange(DynamicBufferRange):
    def __init__(self, buffer, start, size):
        DynamicBufferRange.__init__(self, start, size)
        self._buffer = buffer

    valid = True
    startPosition, size = buildGetters('start', 'length')

    def createCursor(self, offset=0, length=-1):
        if offset >= self.size:
            raise IndexError('offset is out of range')
        return DataCursor(self.startPosition + offset, length)


class CursorInactiveError(Exception):
    def __init__(self):
        Exception.__init__(self, tr('cursor is inactive'))


class CursorNotWriteableError(Exception):
    def __init__(self):
        Exception.__init__(self, tr('cursor is not writeable'))


class AbstractCursor(object):
    """Abstract cursor gives interface to underlying sequence of bytes (buffer). Buffer can be mutable.
    Note that negative indexes given to AbstractCursor has different meaning from negative indexes in standard Python
    sequences. If index is negative, cursor will access bytes from the left of current position. For example,
    if cursor is initialized with buffer containing bytestring b'hello', and current position points to 'o' byte,
    cursor[-3:-2] will return b'e'.
    Access to data outside allowed range results in IndexError.
        cursor = utils.DataCursor(b'hello')  # current offset is 0
        x = cursor[0]  # ok
        x = cursor[-1]  # IndexError
        x = cursor[5]  # IndexError
        x = cursor[-10:4]  # IndexError
        x = cursor[-10:-1]  # IndexError
        x = cursor[0:1000]  # IndexError
        x = cursor[10:100]  # IndexError
        x = cursor[0:]  # b'hello'
        x = cursor[:]  # b'hello'
    """

    def __init__(self, cursor_offset=0, writeable=True, override_buffer_length=-1):
        self._cursorOffset = cursor_offset
        self._writeable = writeable
        self._overrideBufferLength = override_buffer_length

    @property
    def bufferLength(self):
        return self._bufferLength() if self._overrideBufferLength < 0 else self._overrideBufferLength

    def _bufferLength(self):
        raise NotImplementedError()

    @property
    def position(self):
        """Current cursor offset relative to buffer position.
        """
        return self._cursorOffset

    @position.setter
    def position(self, new_value):
        self._cursorOffset = new_value

    offset = position

    @property
    def leftBoundary(self):
        """This is offset of first byte in underlying buffer relative to current cursor position.
        """
        return -self._cursorOffset

    @property
    def rightBoundary(self):
        """This is offset of end (last byte + 1) of underlying buffer relative to current cursor position.
        """
        return self.bufferLength - self._cursorOffset

    @property
    def isAtValidPosition(self):
        """Returns True if cursor is at valid position.
        """
        return 0 <= self._cursorOffset < self.bufferLength

    def __bool__(self):
        return self.isAtValidPosition

    def advance(self, offset_inc):
        """Moves current cursor position by :offset_inc: bytes. If :offset_inc: is negative, moves cursor backwards.
        """
        self._cursorOffset += offset_inc

    @property
    def writeable(self):
        return self._writeable

    def __getitem__(self, index):
        if isinstance(index, slice):
            return self.read(*self._rangeFromSlice(index))
        return self.read(index, index + 1)[0]

    def _rangeFromSlice(self, index):
        return (index.start if index.start is not None else self.leftBoundary,
                index.stop if index.stop is not None else self.rightBoundary)

    def read(self, start, stop):
        return self._read(self._translate(start), self._translate(stop))

    def _read(self, start, stop) -> bytes:
        """This method should correctly handle invalid start and stop arguments. If range is invalid (even partially)
        you should raise IndexError.
        """
        raise NotImplementedError()

    def __setitem__(self, index, data):
        if isinstance(index, slice):
            start, stop = self._rangeFromSlice(index)
            self.replace(start, stop, data)
        else:
            if isinstance(data, int):
                data = data.to_bytes(1, byteorder='big')
            self.replace(index, index + 1, data)

    def replace(self, start, stop, data):
        self._replace(self._translate(start), self._translate(stop), bytes(data))

    def _replace(self, start, stop, data) -> None:
        raise NotImplementedError()

    def write(self, index, data):
        self._write(self._translate(index), bytes(data))

    def _write(self, index, data) -> None:
        raise NotImplementedError()

    def insert(self, index, data):
        self._insert(self._translate(index), data)

    def _insert(self, index, data) -> None:
        raise NotImplementedError()

    def remove(self, start, stop):
        self._remove(self._translate(start), self._translate(stop))

    def _remove(self, start, stop) -> None:
        raise NotImplementedError()

    def __delitem__(self, index):
        if isinstance(index, slice):
            self.remove(*self._rangeFromSlice(index))
        else:
            self.remove(index, index + 1)

    def _translate(self, offset):
        return offset + self._cursorOffset

    @contextlib.contextmanager
    def activate(self):
        self._activate()
        try:
            yield
        finally:
            self._deactivate()

    def _activate(self) -> None:
        pass

    def _deactivate(self) -> None:
        pass

    @property
    def isActive(self):
        return True

    def bufferRange(self, start, stop):
        return self._bufferRange(self._translate(start), self._translate(stop))

    def _bufferRange(self, start, stop) -> DynamicBufferRange:
        raise NotImplementedError()

    def _cloneTo(self, to):
        to._cursorOffset = self._cursorOffset
        to._writeable = self._writeable
        to._overrideBufferLength = self._overrideBufferLength

    def clone(self):
        raise NotImplementedError()

    def limited(self, fore_limit):
        cloned = self.clone()
        cloned._overrideBufferLength = min(fore_limit + cloned.position, cloned.bufferLength)
        return cloned


class DocumentCursor(AbstractCursor):
    def __init__(self, document, cursor_offset=0, writeable=True, override_buffer_length=-1):
        AbstractCursor.__init__(self, cursor_offset, writeable, override_buffer_length)
        self._document = document
        self._activationCount = 0

    @property
    def document(self):
        return self._document

    def _bufferLength(self):
        return self._document.length

    def _read(self, start, stop):
        if 0 <= start < self.bufferLength and start <= stop <= self.bufferLength:
            return bytes(self._document.read(start, stop - start))
        else:
            raise IndexError()

    def _replace(self, start, stop, data):
        import hex.documents as documents
        if (0 <= start <= MaximalPosition and start <= stop <= MaximalPosition + 1 and
                                                                    start + len(data) <= MaximalPosition + 1):
            span = documents.DataSpan(data)
            if stop == start:
                self._document.insertSpan(start, span)
            else:
                self._document.beginComplexAction()
                try:
                    self._document.remove(start, stop - start)
                    self._document.insertSpan(start, span)
                finally:
                    self._document.endComplexAction()
        else:
            raise IndexError()

    def _write(self, start, data):
        if 0 <= start <= MaximalPosition and start + len(data) <= MaximalPosition + 1:
            import hex.documents as documents
            self._document.writeSpan(start, documents.DataSpan(data))
        else:
            raise IndexError()

    def _insert(self, start, data):
        if 0 <= start <= MaximalPosition and start + len(data) <= MaximalPosition + 1:
            import hex.docuents as documents
            self._document.insertSpan(start, documents.DataSpan(data))
        else:
            raise IndexError()

    def _remove(self, start, stop):
        if 0 <= start <= MaximalPosition and start <= stop <= MaximalPosition + 1:
            self._document.remove(start, stop - start)
        else:
            raise IndexError()

    @property
    def isActive(self):
        return self._activationCount > 0

    def _activate(self):
        self._activationCount += 1

    def _deactivate(self):
        if self._activationCount <= 0:
            raise CursorInactiveError()
        self._activationCount -= 1

    def _bufferRange(self, start, stop):
        if 0 <= start <= MaximalPosition and start <= stop <= MaximalPosition + 1:
            return DocumentRange(self._document, start, stop - start)
        raise IndexError()

    def clone(self):
        cloned = DocumentCursor(self.document)
        self._cloneTo(cloned)
        return cloned


class DataCursor(AbstractCursor):
    def __init__(self, data, cursor_offset=0, override_buffer_length=-1):
        AbstractCursor.__init__(self, cursor_offset, writeable=False, override_buffer_length=override_buffer_length)
        self._data = data

    def _bufferLength(self):
        return len(self._data)

    @property
    def data(self):
        return self._data

    def _read(self, start, stop):
        if 0 <= start < self.bufferLength and start <= stop <= self.bufferLength:
            return self._data[start:stop]
        else:
            raise IndexError()

    def clone(self):
        cloned = DataCursor(self._data)
        self._cloneTo(cloned)
        return cloned

    def _bufferRange(self, start, stop):
        if 0 <= start and (len(self._data) == 0 or start < len(self._data)) and start <= stop <= len(self._data):
            return DataRange(self._data, start, stop - start)
        raise IndexError()


def createSingleton(object_type, force_app_thread=True):
    managed_object = None

    def return_func():
        nonlocal managed_object
        if managed_object is None:
            managed_object = object_type()
            if force_app_thread and isinstance(managed_object, QObject):
                managed_object.moveToThread(qApp.thread())
        return managed_object

    return return_func


import builtins

if hasattr(builtins, 'callable'):
    def isCallable(obj):
        return callable(obj)
else:
    def isCallable(obj):
        return hasattr(obj, '__call__')

