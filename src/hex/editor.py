import copy
import threading
import contextlib
from PyQt4.QtCore import pyqtSignal, QObject, QByteArray
import hex.utils as utils


class OutOfBoundsError(ValueError):
    def __init__(self):
        ValueError.__init__(self, 'position is out of bounds')


class EditorError(IOError):
    pass


class ReadOnlyError(EditorError):
    def __init__(self):
        EditorError.__init__(self, utils.tr('operation not allowed for editor in read-only mode'))


class FreezeSizeError(EditorError):
    def __init__(self):
        EditorError.__init__(self, utils.tr('operation is not allowed for editor with frozen size'))


DefaultFillPattern = b'\0'


class Span(object):
    """Span controls piece of immutable data. Spans are immutable and thread-safe.
    """
    def __init__(self, parent=None):
        self.__parent = parent
        self._lock = threading.RLock()
        self.savepoint = -1

    @property
    def lock(self):
        return self._lock

    @property
    def parent(self):
        return self.__parent

    @property
    def length(self):
        raise NotImplementedError()

    def read(self, offset, size):
        raise NotImplementedError()

    def split(self, offset):
        with self.lock:
            if offset < 0 or offset >= len(self):
                raise OutOfBoundsError()
            return self.clone(self.parent), self.clone(self.parent)

    def clone(self, new_parent):
        with self.lock:
            cloned = copy.deepcopy(self)
            cloned.__parent = new_parent
            return cloned

    def __len__(self):
        return self.length

    def isRangeValid(self, offset, size):
        return 0 <= offset and 0 <= size and offset + size <= self.length


class DataSpan(Span):
    def __init__(self, parent, data):
        Span.__init__(self, parent)
        if not isinstance(data, (bytes, QByteArray)):
            raise TypeError()
        self.__data = bytes(data)  # should be bytes object

    @property
    def length(self):
        with self.lock:
            return len(self.__data)

    def read(self, offset, size):
        with self.lock:
            if not self.isRangeValid(offset, size):
                raise OutOfBoundsError()
            return self.__data[offset:offset+size]

    def split(self, offset):
        with self.lock:
            f, s = Span.split(self, offset)
            f.__data = self.__data[:offset]
            s.__data = self.__data[offset:]
            return f, s

    def __deepcopy__(self, memo):
        with self.lock:
            cloned = DataSpan(self.parent, self.__data)
            cloned.savepoint = self.savepoint
            return cloned

    def __eq__(self, other):
        if not isinstance(other, DataSpan):
            return NotImplemented
        return self.__data == other.__data


class DeviceSpan(Span):
    def __init__(self, parent, device, device_offset, device_len):
        Span.__init__(self, parent)
        self._device = device
        self._deviceOffset = device_offset
        self._deviceLen = device_len if device_len >= 0 else -1

    @property
    def length(self):
        with self.lock:
            return self._deviceLen

    def read(self, offset, size):
        with self.lock:
            if not self.isRangeValid(offset, size):
                raise OutOfBoundsError()
            if self._device is None:
                return bytes()
            with self._device.lock:
                device_length = self.length
                if device_length >= 0:
                    return self._device.read(self._deviceOffset + offset, size)
                else:
                    return bytes()

    def split(self, offset):
        f, s = Span.split(self, offset)
        f._deviceLen = offset
        s._deviceOffset = self._deviceOffset + offset
        s._deviceLen = len(self) - offset if self._deviceLen >= 0 else -1
        return f, s

    def __deepcopy__(self, memo):
        with self.lock:
            cloned = DeviceSpan(self.parent, self._device, self._deviceOffset, self._deviceLen)
            cloned.savepoint = self.savepoint
            return cloned

    def __eq__(self, other):
        if not isinstance(other, DeviceSpan):
            return NotImplemented
        return self._device is other._device and self._deviceOffset == other._deviceOffset and \
                    self._deviceLen == other._deviceLen

    @property
    def device(self):
        return self._device


class FillSpan(Span):
    def __init__(self, parent, pattern, length):
        Span.__init__(self, parent)
        self.__pattern = pattern
        self.__length = length

    @property
    def length(self):
        with self.lock:
            return self.__length * len(self.__pattern)

    def read(self, offset, size):
        with self.lock:
            if not self.isRangeValid(offset, size):
                raise OutOfBoundsError()
            rem = size % len(self.__pattern)
            return self.__pattern * (size // len(self.__pattern)) + self.__pattern[:rem]

    def split(self, offset):
        s, f = Span.split(self, offset)
        f.__length = offset
        s.__length = self.__length - offset
        return f, s

    def __deepcopy__(self, memo):
        with self.lock:
            cloned = FillSpan(self.parent, self.__pattern, self.__length)
            cloned.savepoint = self.savepoint
            return cloned

    def __eq__(self, other):
        if not isinstance(other, FillSpan):
            return NotImplemented
        return self.__pattern == other.__pattern and self.__length == other.__length


class Editor(QObject):
    dataChanged = pyqtSignal(int, int)  # first argument is start position, second one - length
    bytesInserted = pyqtSignal(int, int)
    bytesRemoved = pyqtSignal(int, int)
    resized = pyqtSignal(int)
    canUndoChanged = pyqtSignal(bool)
    canRedoChanged = pyqtSignal(bool)
    isModifiedChanged = pyqtSignal(bool)
    urlChanged = pyqtSignal(object)

    def __init__(self, device):
        QObject.__init__(self)
        self._device = device
        self._lock = utils.ReadWriteLock()
        self._totalLength = 0
        self._currentUndoAction = None
        self._disableUndo = False
        self._spans = []
        self._freezeSize = device.fixedSize
        self._readOnly = device.readOnly
        self._canQuickSave = True
        self._currentAtomicOperationIndex = 0
        self._savepoint = 0

        if len(self._device):
            # initialize editor with one span referencing all device data
            self._spans.append(DeviceSpan(self, self._device, 0, len(self._device)))
            self._spans[0].savepoint = 0
            self._totalLength = len(self._device)

        self._currentUndoAction = ComplexAction(self, utils.tr('initial state'))
        self._device.urlChanged.connect(self.urlChanged)

        self._device.editor = self

    @property
    def lock(self):
        return self._lock

    @property
    def device(self):
        return self._device

    @property
    def url(self):
        return self._device.url

    @property
    def length(self):
        return self._totalLength

    @property
    def fixedSize(self):
        return self._freezeSize

    @fixedSize.setter
    def fixedSize(self, new_freeze):
        self._freezeSize = new_freeze

    @property
    def readOnly(self):
        return self._readOnly

    @readOnly.setter
    def readOnly(self, new_read_only):
        self._readOnly = new_read_only

    def readExact(self, position, length):
        """Read :length: bytes starting from byte with index :position:
        Always returns byte array with :length: elements.
        Raises OutOfBoundsError if :position: is not valid or there are less than :length: bytes available.
        """

        with self.lock.read:
            if position < 0 or length < 0 or position + length > len(self):
                raise OutOfBoundsError()
            spans, left_offset, right_offset = self.spansInRange(position, length)
            result = bytes()
            for span_index in range(len(spans)):
                pos = left_offset if span_index == 0 else 0
                size = (right_offset - pos) + 1 if span_index == len(spans) - 1 else len(spans[span_index]) - pos
                result += spans[span_index].read(pos, size)
            return result

    def read(self, position, length):
        """Reads data at :position:, but unlike Editor.readExact, does not fail when no :length: bytes can be read. It
        reads as much data as possible but maximal :length: bytes.
        """

        with self.lock.read:
            if position < 0 or length < 0:
                raise OutOfBoundsError()
            if position >= len(self):
                return b''
            elif position + length > len(self):
                length = len(self) - position
            return self.readExact(position, length)

    def readAll(self):
        """Read all data from editor. Can raise MemoryError, of course."""

        with self.lock.read:
            result = bytes()
            for span in self.spans:
                result += span.read(0, len(span))
            return result

    @property
    def spans(self):
        """Copy of list of all spans in editor"""
        with self.lock.read:
            return self._spans[:]

    def spanAtPosition(self, position):
        """Get span that holds byte at :position:.
        """

        with self.lock.read:
            span_index = self._findSpanIndex(position)[0]
            return self._spans[span_index] if span_index >= 0 else None

    def spansInRange(self, position, length):
        """Get list of spans in given range. Returns tuple (spans, left_offset, right_offset).
        First and last span boundaries can be not exactly (position, position + length - 1).
        If range is out of editor size, empty list will be returned.
        First span in returned list always holds byte at :position: and last span holds byte at :position: + :length: - 1
        """

        with self.lock.read:
            if position < 0 or length < 0 or position + length > len(self):
                raise OutOfBoundsError()

            if not self._spans or length == 0:
                return [], 0, 0

            first_span_index, left_offset = self._findSpanIndex(position)
            last_span_index, right_offset = self._findSpanIndex(position + length - 1)
            assert(first_span_index >= 0 and last_span_index >= 0)
            return self._spans[first_span_index:last_span_index+1], left_offset, right_offset

    def takeSpans(self, position, length):
        """Same as Editor.spansInRange, but first splits spans at boundaries, so first span always starts with byte
        at :position: and last one always ends with byte at :position: + :length: - 1.
        Returns list of spans.
        """

        with self.lock.write:
            if position < 0 or length < 0 or position + length > len(self):
                raise OutOfBoundsError()

            if not self._spans or length == 0:
                return []

            self.splitSpans(position)
            self.splitSpans(position + length)
            return self.spansInRange(position, length)[0]

    def insertSpan(self, position, span, fill_pattern=DefaultFillPattern):
        """Shorthand method for Editor.insertSpans
        """
        self.insertSpans(position, [span], fill_pattern)

    def insertSpans(self, position, spans, fill_pattern=DefaultFillPattern, undo=False):
        """Insert list of spans into given :position:. After inserting, first byte of first span in list will have
        :position: index in editor. If :position: > self.length, space between end of editor data and insertion point
        will be occupied by FillSpan initialized by :fill_pattern:. If :fill_pattern: is None, method will raise
        OutOfBoundsError if :position: > self.length.
        Spans in given list are cloned before inserting.
        Raises OutOfBoundsError is :position: is negative.
        """

        with self.lock.write:
            if self._readOnly:
                raise ReadOnlyError()

            if position != 0 and self._freezeSize:
                raise FreezeSizeError()

            old_length = self._totalLength
            self._insertSpans(position, spans, fill_pattern, undo)

            if self._canQuickSave:
                if position < old_length or any(isinstance(span, DeviceSpan) and span._device is self._device for span in spans):
                    self._canQuickSave = False

            if old_length != self._totalLength:
                self.resized.emit(self._totalLength)
                self.bytesInserted.emit(position, self._totalLength - old_length)
                self.dataChanged.emit(min(old_length, position), -1)

    def _insertSpans(self, position, spans, fill_pattern=DefaultFillPattern, undo=False):
        if position < 0 or (fill_pattern is None and position > self._totalLength):
            raise OutOfBoundsError()

        if not spans:
            return

        if position < self._totalLength:
            self.splitSpans(position)
            span_index = self._findSpanIndex(position)[0]
        elif position == self._totalLength:
            span_index = len(self._spans)
        else:
            spans = [FillSpan(self, copy.deepcopy(fill_pattern), position - self._totalLength)] + spans
            position = self._totalLength
            span_index = len(self._spans)

        insertion_length = 0
        for span in spans:
            cloned_span = span.clone(self)
            if not undo:
                cloned_span.savepoint = -1

            self._spans.insert(span_index, cloned_span)
            span_index += 1
            insertion_length += len(cloned_span)

        self._totalLength += insertion_length

        if not undo:
            self.addAction(InsertAction(self, position, spans, insertion_length))
        self._incrementAtomicOperationIndex(-1 if undo else 1)

    def appendSpan(self, span):
        """Shorthand method for Editor.insertSpan
        """
        with self.lock.write:
            self.insertSpan(self._totalLength, span)

    def appendSpans(self, spans):
        """Shorthand method for Editor.insertSpans
        """
        with self.lock.write:
            self.insertSpans(self._totalLength, spans)

    def writeSpan(self, position, span, fill_pattern=DefaultFillPattern):
        """Shorthand method for Editor.writeSpans
        """
        self.writeSpans(position, [span], fill_pattern)

    def writeSpans(self, position, spans, fill_pattern=DefaultFillPattern):
        """Overwrites data starting from :position: with given span list. Spans are cloned before inserting.
        If position is out of editor data, editor will be resized, and space between old end of data and write position
        will be occupied by FillSpan initialized with :fill_pattern:. If :fill_pattern: is None, raises OutOfBoundsError
        if :position: > self.length. Raises OutOfBoundsError if position < 0.
        """

        with self.lock.write:
            if self._readOnly:
                raise ReadOnlyError()

            if position < 0:
                raise OutOfBoundsError()

            old_length = self._totalLength
            write_length = self._calculateSpansLength(spans)
            old_can_quick_save = self._canQuickSave

            if self._freezeSize and position + write_length > self._totalLength:
                raise FreezeSizeError()

            try:
                self.beginComplexAction(utils.tr('writing {0} bytes at position {1}').format(write_length, position))
                if position < self._totalLength:
                    self._remove(position, write_length)
                self._insertSpans(position, spans, fill_pattern)
            finally:
                self.endComplexAction()

            if old_can_quick_save:
                self._canQuickSave = not any(isinstance(span, DeviceSpan) and span._device is self._device for span in spans)

            if self._totalLength != old_length:
                self.resized.emit(self._totalLength)
                self.dataChanged.emit(min(position, old_length), -1)
            else:
                self.dataChanged.emit(position, write_length)

    def _remove(self, position, length, undo=False):
        if position < 0:
            raise OutOfBoundsError()
        if not self._spans or not length or position >= self._totalLength:
            return
        if length < 0 or self._totalLength == 0 or position + length >= self._totalLength:
            length = len(self) - position

        removed_spans = self.takeSpans(position, length)
        first_span_index = self._findSpanIndex(position)[0]
        last_span_index = first_span_index + len(removed_spans)
        del self._spans[first_span_index:last_span_index]

        self._totalLength -= length

        if not undo:
            self.addAction(RemoveAction(self, position, removed_spans, length))
        self._incrementAtomicOperationIndex(-1 if undo else 1)

    def remove(self, position, length, undo=False):
        """Remove :length: bytes starting from byte with index :position:. If length < 0, removes all bytes from
        :position: until end. If less then :length: bytes available, also removes all bytes until end.
        Raises OutOfBoundsError if position is negative or :position: >= self.length.
        """

        with self.lock.write:
            if self._readOnly:
                raise ReadOnlyError()
            if self._freezeSize and length != 0:
                raise FreezeSizeError()

            if length == 0:
                return

            old_length = self._totalLength

            self._remove(position, length, undo)

            if self._canQuickSave and position + length < old_length:
                self._canQuickSave = False

            self.resized.emit(len(self))
            self.bytesRemoved.emit(position, length)
            self.dataChanged.emit(position, -1)

    @property
    def isModified(self):
        with self.lock.read:
            return self._currentAtomicOperationIndex != self._savepoint

    @isModified.setter
    def isModified(self, new_modified):
        with self.lock.write:
            if self.isModified != new_modified:
                self._incrementAtomicOperationIndex()

    def isRangeModified(self, position, length=1):
        with self.lock.read:
            if not self.isModified:
                return False
            if position >= self._totalLength:
                return False
            elif position + length >= self._totalLength:
                length = self._totalLength - position
            return any(s.savepoint != self._savepoint for s in self.spansInRange(position, length)[0])

    def __len__(self):
        with self.lock.read:
            return self._totalLength

    def _findSpanIndex(self, position):
        """Find span byte with given position is located in
        """
        if not self._spans or position < 0 or position >= len(self):
            return -1, 0

        cpos = 0
        for span_index in range(len(self._spans)):
            span = self._spans[span_index]
            if position >= cpos and position < cpos + len(span):
                return span_index, position - cpos
            cpos += len(span)
        else:
            return -1, 0

    def splitSpans(self, position):
        """Ensure that byte with given position is first byte in span. If not, split span with this byte into two.
        """
        span_index, offset = self._findSpanIndex(position)
        if span_index >= 0 and offset != 0:
            span = self._spans[span_index]
            splitted = span.split(offset)

            del self._spans[span_index]
            self._spans.insert(span_index, splitted[1])
            self._spans.insert(span_index, splitted[0])

    @staticmethod
    def _calculateSpansLength(spans):
        result = 0
        for span in spans:
            result += len(span)
        return result

    def clear(self):
        with self.lock.write:
            if self._spans:
                self._spans = []
                self._totalLength = 0
                self.dataChanged.emit(0, -1)
                self.resized.emit(0)

    def bytesRange(self, range_start, range_end):
        """Allows iterating over bytes in given range"""
        with self.lock.read:
            for position in range(range_start, range_end):
                try:
                    yield self.read(position, 1)
                except OutOfBoundsError:
                    break

    def addAction(self, action):
        with self.lock.write:
            if not self._disableUndo:
                old_can_undo = self.canUndo()
                self._currentUndoAction.addAction(action)
                if old_can_undo != self.canUndo():
                    self.canUndoChanged.emit(self.canUndo())

    def beginComplexAction(self, title=''):
        with self.lock.write:
            if not self._disableUndo:
                complex_action = ComplexAction(self, title)
                self._currentUndoAction.addAction(complex_action)
                self._currentUndoAction = complex_action

    def endComplexAction(self):
        with self.lock.write:
            if not self._disableUndo:
                if self._currentUndoAction.parent is None:
                    raise ValueError('cannot end complex action while one is not started')
                self._currentUndoAction = self._currentUndoAction.parent

    def undo(self):
        with self.lock.write:
            old_can_undo = self.canUndo()
            old_can_redo = self.canRedo()
            try:
                self._disableUndo = True
                self._currentUndoAction.undoStep()
            finally:
                self._disableUndo = False
            if old_can_undo != self.canUndo():
                self.canUndoChanged.emit(self.canUndo())
            if old_can_redo != self.canRedo():
                self.canRedoChanged.emit(self.canRedo())

    def redo(self, branch=None):
        with self.lock.write:
            old_can_undo = self.canUndo()
            old_can_redo = self.canRedo()
            try:
                self._disableUndo = True
                self._currentUndoAction.redoStep(branch)
            finally:
                self._disableUndo = False
            if old_can_undo != self.canUndo():
                self.canUndoChanged.emit(self.canUndo())
            if old_can_redo != self.canRedo():
                self.canRedoChanged.emit(self.canRedo())

    def canUndo(self):
        with self.lock.read:
            return self._currentUndoAction.canUndo()

    def canRedo(self):
        with self.lock.read:
            return self._currentUndoAction.canRedo()

    def alternativeBranches(self):
        with self.lock.read:
            return self._currentUndoAction.alternativeBranches()

    @property
    def canQuickSave(self):
        with self.lock.read:
            return self._canQuickSave

    def save(self, device=None, switch_device=False):
        """Completely writes all editor data into given device.
        """
        with self.lock.write:
            if device is None:
                if not self.isModified:
                    return
                device = self.device

            if device is None:
                raise ValueError('device is None')

            saver = device.createSaver(self, self.device)
            saver.begin()
            try:
                for span in self._spans:
                    saver.putSpan(span)
            except:
                saver.fail()
                raise
            else:
                saver.complete()
                if device is self._device or switch_device:
                    self._setSavepoint()

                if switch_device:
                    for span in self._spans:
                        if isinstance(span, DeviceSpan) and span._device is self._device:
                            span._device = device
                    self._setSavepoint()

                    self._device = device
                    self.urlChanged.emit(self.url)

    def _setSavepoint(self):
        if self._savepoint != self._currentAtomicOperationIndex:
            self._savepoint = self._currentAtomicOperationIndex
            for span in self._spans:
                span.savepoint = self._savepoint
            self.isModifiedChanged.emit(self.isModified)

    def _incrementAtomicOperationIndex(self, increment=1):
        was_modified = self.isModified
        self._currentAtomicOperationIndex += increment
        if was_modified != self.isModified:
            self.isModifiedChanged.emit(self.isModified)

    def createReadCursor(self, initial_position=0):
        return EditorCursor(self, initial_position, read_only=True)

    def createWriteCursor(self, initial_position=0):
        return EditorCursor(self, initial_position, read_only=False)


class AbstractUndoAction(object):
    def __init__(self, editor, title=''):
        self.title = title
        self.editor = editor
        self.parent = None

    def _restore(self):
        pass

    def undo(self):
        self._restore()

    def redo(self):
        self._restore()


class InsertAction(AbstractUndoAction):
    def __init__(self, editor, position, spans, length, title=''):
        if not title:
            title = utils.tr('insert {0} bytes from position {1}'.format(editor._calculateSpansLength(spans), position))
        AbstractUndoAction.__init__(self, editor, title)
        self.spans = spans
        self.position = position
        self.length = length

    def undo(self):
        # just remove inserted spans...
        self.editor.remove(self.position, self.length, undo=True)
        AbstractUndoAction.undo(self)

    def redo(self):
        self.editor.insertSpans(self.position, self.spans)
        AbstractUndoAction.redo(self)


class RemoveAction(AbstractUndoAction):
    def __init__(self, editor, position, spans, length, title=''):
        if not title:
            title = utils.tr('remove {0} bytes from position {1}'.format(editor._calculateSpansLength(spans), position))
        AbstractUndoAction.__init__(self, editor, title)
        self.spans = spans
        self.position = position
        self.length = length

    def undo(self):
        # insert them back
        self.editor.insertSpans(self.position, self.spans, undo=True)
        AbstractUndoAction.undo(self)

    def redo(self):
        self.editor.remove(self.position, self.length)
        AbstractUndoAction.redo(self)


class ComplexAction(AbstractUndoAction):
    class Branch(object):
        def __init__(self, actions, start_index):
            self.actions = actions
            self.startIndex = start_index

    def __init__(self, editor, title=''):
        AbstractUndoAction.__init__(self, editor, title)
        self.subActions = []
        self.currentStep = -1
        self.branches = []

    def undoStep(self):
        if self.currentStep >= 0:
            self.subActions[self.currentStep].undo()
            self.currentStep -= 1

    def redoStep(self, branch=None):
        if self.currentStep + 1 != len(self.subActions):
            if branch is not None:
                # try to switch to another branch
                if not any(b is branch for b in self.branches) or branch.startIndex != self.currentStep + 1 or not branch.actions:
                    raise ValueError('failed to switch to another redo branch: no such branch after current action')
                # yeah, we can switch to it
                self.branches = [b for b in self.branches if b is not branch]
                self._backoffCurrentBranch()
                self.subActions += branch.actions
            self.subActions[self.currentStep + 1].redo()
            self.currentStep += 1

    def _backoffCurrentBranch(self):
        if self.currentStep + 1 != len(self.subActions):
            new_branch = self.Branch(self.subActions[self.currentStep + 1:], self.currentStep + 1)
            self.branches.append(new_branch)
            del self.subActions[self.currentStep + 1:]

    def undo(self):
        if self.currentStep >= 0:
            for action in self.subActions[:self.currentStep + 1][::-1]:
                action.undo()
                self.currentStep -= 1

    def redo(self):
        for action in self.subActions[self.currentStep + 1:]:
            action.redo()
            self.currentStep += 1

    def addAction(self, action):
        if action is not None:
            action.parent = self
            self._backoffCurrentBranch()
            self.subActions.append(action)
            self.currentStep = len(self.subActions) - 1

    def canUndo(self):
        return self.currentStep >= 0

    def canRedo(self):
        return self.currentStep + 1 != len(self.subActions)

    def alternativeBranches(self):
        return [branch for branch in self.branches if branch.startIndex == self.currentStep + 1]

    @property
    def wasModified(self):
        return bool(self.currentStep >= 0 and self.subActions[self.currentStep]._wasModified)


class AbstractCursor(object):
    def __init__(self):
        self._length = -1
        self._pos = 0
        self._activationCount = 0

    @property
    def minimal(self):
        return -self._pos

    @property
    def maximal(self):
        if self._length < 0:
            return -1
        else:
            return self._length - self._pos - 1

    @property
    def position(self):
        return self._pos

    @position.setter
    def position(self, new_pos):
        if new_pos != self._pos:
            if self._pos < self.minimal:
                self._pos = self.minimal
            elif self.maximal >= 0 and self._pos > self.maximal:
                self._pos = self.maximal
            else:
                self._pos = new_pos

    @property
    def readOnly(self):
        raise NotImplementedError()

    def __getitem__(self, index):
        if isinstance(index, slice):
            return self.read(index.start, index.stop)
        else:
            d = self.read(index, index + 1)
            return d[0] if len(d) == 1 else d

    def _adjustSlice(self, start, stop):
        return max(start, self.minimal), (min(stop, self.maximal + 1) if self.maximal >= 0 else stop)

    def read(self, start, stop):
        if not self.isActive:
            raise CursorInactiveError()
        start, stop = self._adjustSlice(start, stop)
        if start >= stop:
            return b''
        return self._read(start, stop)

    def _read(self, start, stop):
        raise NotImplementedError()

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            self.write(index.start, index.stop, value)
        else:
            if isinstance(value, int):
                d = value.to_bytes(1, byteorder='big')
            else:
                d = bytes(value)
            self.write(index, index + 1, d)

    def write(self, start, stop, value):
        if not self.isActive:
            raise CursorInactiveError()
        if self.readOnly:
            raise ReadOnlyError()
        start, stop = self._adjustSlice(start, stop)
        if start > stop:
            return
        return self._write(start, stop, value)

    def _write(self, start, stop, value):
        raise NotImplementedError()

    def _toOffset(self, value):
        return self._pos + value

    @contextlib.contextmanager
    def activate(self):
        self._activate()
        try:
            yield
        finally:
            self._deactivate()

    @property
    def isActive(self):
        return self._activationCount > 0

    def _activate(self):
        self._activationCount += 1

    def _deactivate(self):
        self._activationCount -= 1

    def get(self, length=1):
        data = self[0:length]
        self._pos += len(data)
        return data

    def put(self, data):
        self[0:0] = data
        self._pos += len(data)


class CursorInactiveError(IOError):
    pass


class EditorCursor(AbstractCursor):
    def __init__(self, editor, position, read_only):
        AbstractCursor.__init__(self)
        self._editor = editor
        self._readOnly = read_only
        self._pos = position
        self._spanIndex = -1

    @property
    def readOnly(self):
        return self._readOnly

    def _read(self, start, stop):
        return self._editor.read(self._toOffset(start), stop - start)

    def _write(self, start, stop, value):
        if stop - start == len(value):
            self._editor.writeSpan(self._toOffset(start), DataSpan(self._editor, value))
        else:
            self._editor.beginComplexAction()
            try:
                self._editor.remove(self._toOffset(start), stop - start)
                self._editor.insertSpan(self._toOffset(start), DataSpan(self._editor, value))
            finally:
                self._editor.endComplexAction()

    def _activate(self):
        if self._readOnly:
            self._editor.lock.acquireRead()
        else:
            self._editor.lock.acquireWrite()
        AbstractCursor._activate(self)

    def _deactivate(self):
        if self._readOnly:
            self._editor.lock.releaseRead()
        else:
            self._editor.lock.releaseWrite()
        AbstractCursor._deactivate(self)

