import copy
import threading
from PyQt4.QtCore import pyqtSignal, QObject
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
        self.savepointIndex = -1

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
        self.__data = data  # should be bytes object

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
            cloned.savepointIndex = self.savepointIndex
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
            cloned.savepointIndex = self.savepointIndex
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
            cloned.savepointIndex = self.savepointIndex
            return cloned

    def __eq__(self, other):
        if not isinstance(other, FillSpan):
            return NotImplemented
        return self.__pattern == other.__pattern and self.__length == other.__length


class Editor(QObject):
    dataChanged = pyqtSignal(int, int)  # first argument is start position, second one - length
    resized = pyqtSignal(int)
    canUndoChanged = pyqtSignal(bool)
    canRedoChanged = pyqtSignal(bool)
    isModifiedChanged = pyqtSignal(bool)
    urlChanged = pyqtSignal(object)

    def __init__(self, device):
        QObject.__init__(self)
        self._device = device
        self._lock = threading.RLock()
        self._modified = False
        self._totalLength = 0
        self._currentUndoAction = None
        self._disableUndo = False
        self._spans = []
        self._freezeSize = device.fixedSize
        self._readOnly = device.readOnly
        self._canQuickSave = True
        self._currentSavepointIndex = 0

        if len(self._device):
            # initialize editor with one span referencing all device data
            self._spans.append(DeviceSpan(self, self._device, 0, len(self._device)))
            self._spans[0].savepointIndex = -1
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

    def read(self, position, length):
        """Read :length: bytes starting from byte with index :position:
        Always returns byte array with :length: elements.
        Raises OutOfBoundsError if :position: is not valid or there are less than :length: bytes available.
        """

        with self.lock:
            if position < 0 or length < 0 or position + length > len(self):
                raise OutOfBoundsError()
            spans, left_offset, right_offset = self.spansInRange(position, length)
            result = bytes()
            for span_index in range(len(spans)):
                pos = left_offset if span_index == 0 else 0
                size = (right_offset - pos) + 1 if span_index == len(spans) - 1 else len(spans[span_index]) - pos
                result += spans[span_index].read(pos, size)
            return result

    def readAtEnd(self, position, length):
        """Reads data at :position:, but unlike Editor.read, does not fails when no :length: bytes can be read. It
        reads as much data as possible but maximal :length: bytes. Still fails if :position: is invalid
        or :length: < 0.
        """

        with self.lock:
            if position < 0 or length < 0 or position >= len(self):
                raise OutOfBoundsError()
            if position + length > len(self):
                length = len(self) - position
            return self.read(position, length)

    def readAll(self):
        """Read all data from editor. Can raise MemoryError, of course."""

        with self.lock:
            result = bytes()
            for span in self.spans:
                result += span.read(0, len(span))
            return result

    @property
    def spans(self):
        """Copy of list of all spans in editor"""
        with self.lock:
            return copy.deepcopy(self._spans)

    def spanAtPosition(self, position):
        """Get span that holds byte at :position:.
        """

        with self.lock:
            span_index = self._findSpanIndex(position)[0]
            return self._spans[span_index] if span_index >= 0 else None

    def spansInRange(self, position, length):
        """Get list of spans in given range. Returns tuple (spans, left_offset, right_offset).
        First and last span boundaries can be not exactly (position, position + length - 1).
        If range is out of editor size, empty list will be returned.
        First span in returned list always holds byte at :position: and last span holds byte at :position: + :length: - 1
        """

        with self.lock:
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

        with self.lock:
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

    def insertSpans(self, position, spans, fill_pattern=DefaultFillPattern):
        """Insert list of spans into given :position:. After inserting, first byte of first span in list will have
        :position: index in editor. If :position: > self.length, space between end of editor data and insertion point
        will be occupied by FillSpan initialized by :fill_pattern:. If :fill_pattern: is None, method will raise
        OutOfBoundsError if :position: > self.length.
        Spans in given list are cloned before inserting.
        Raises OutOfBoundsError is :position: is negative.
        """

        if self._readOnly:
            raise ReadOnlyError()

        if position != 0 and self._freezeSize:
            raise FreezeSizeError()

        old_length = self._totalLength
        self._insertSpans(position, spans, fill_pattern)

        if self._canQuickSave:
            if position < old_length or any(isinstance(span, DeviceSpan) and span._device is self._device for span in spans):
                self._canQuickSave = False

        if old_length != self._totalLength:
            self.resized.emit(self._totalLength)
            self.dataChanged.emit(min(old_length, position), -1)

    def _insertSpans(self, position, spans, fill_pattern=DefaultFillPattern):
        with self.lock:
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

            for span in spans:
                cloned_span = span.clone(self)
                cloned_span.savepointIndex = self._currentSavepointIndex
                self._spans.insert(span_index, cloned_span)
                span_index += 1
                self._totalLength += len(cloned_span)  # wow, exception safety...

            self.addAction(InsertAction(self, position, spans))
            self.isModified = True

    def appendSpan(self, span):
        """Shorthand method for Editor.insertSpan
        """
        with self.lock:
            self.insertSpan(self._totalLength, span)

    def appendSpans(self, spans):
        """Shorthand method for Editor.insertSpans
        """
        with self.lock:
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

    def _remove(self, position, length):
        if position < 0:
            raise OutOfBoundsError()
        if not self._spans or not length or position >= self._totalLength:
            return
        if length < 0 or self._totalLength == 0 or position + length >= self._totalLength:
            length = len(self) - position

        removed_spans = self.takeSpans(position, length)
        first_span_index = self._findSpanIndex(position)[0]
        last_span_index = self._findSpanIndex(position + length - 1)[0] + 1
        del self._spans[first_span_index:last_span_index]

        self._totalLength -= length

        self.addAction(RemoveAction(self, position, removed_spans))
        self.isModified = True

    def remove(self, position, length):
        """Remove :length: bytes starting from byte with index :position:. If length < 0, removes all bytes from
        :position: until end. If less then :length: bytes available, also removes all bytes until end.
        Raises OutOfBoundsError if position is negative or :position: >= self.length.
        """

        if self._readOnly:
            raise ReadOnlyError()
        if self._freezeSize and length != 0:
            raise FreezeSizeError()

        old_length = self._totalLength

        self._remove(position, length)

        if self._canQuickSave and position + length < old_length:
            self._canQuickSave = False

        self.resized.emit(len(self))
        self.dataChanged.emit(position, -1)

    def removeSpans(self, position, span_count):
        if self._readOnly:
            raise ReadOnlyError()
        if self._freezeSize and span_count:
            raise FreezeSizeError()

        if span_count < 0:
            raise ValueError()

        span_index, span_offset = self._findSpanIndex(position)
        if span_index < 0 or span_offset != 0 or span_index + span_count > len(self._spans):
            raise ValueError()

        remove_length = self._calculateSpansLength(self._spans[span_index:span_index + span_count])
        if not remove_length:
            return

        del self._spans[span_index:span_index + span_count]
        self._totalLength -= remove_length

        self.resized.emit(self._totalLength)
        self.dataChanged.emit(position, -1)

    @property
    def isModified(self):
        return self._modified

    @isModified.setter
    def isModified(self, new_modified):
        if self._modified != new_modified:
            self._modified = new_modified
            self.isModifiedChanged.emit(new_modified)

    def isRangeModified(self, position, length=1):
        if not self._modified:
            return False
        return any(s.savepointIndex >= self._currentSavepointIndex for s in self.spansInRange(position, length)[0])

    def __len__(self):
        with self.lock:
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
        with self.lock:
            if self._spans:
                self._spans = []
                self._totalLength = 0
                self.dataChanged.emit(0, -1)
                self.resized.emit(0)

    def bytesRange(self, range_start, range_end):
        """Allows iterating over bytes in given range"""
        for position in range(range_start, range_end):
            try:
                yield self.read(position, 1)
            except OutOfBoundsError:
                break

    def addAction(self, action):
        if not self._disableUndo:
            old_can_undo = self.canUndo()
            self._currentUndoAction.addAction(action)
            if old_can_undo != self.canUndo():
                self.canUndoChanged.emit(self.canUndo())

    def beginComplexAction(self, title=''):
        if not self._disableUndo:
            complex_action = ComplexAction(self, title)
            self._currentUndoAction.addAction(complex_action)
            self._currentUndoAction = complex_action

    def endComplexAction(self):
        if not self._disableUndo:
            if self._currentUndoAction.parent is None:
                raise ValueError('cannot end complex action while one is not started')
            self._currentUndoAction = self._currentUndoAction.parent

    def undo(self):
        old_can_undo = self.canUndo()
        try:
            self._disableUndo = True
            self._currentUndoAction.undoStep()
            new_modified = self._currentUndoAction.wasModified
        finally:
            self._disableUndo = False
        self.isModified = new_modified
        if old_can_undo != self.canUndo():
            self.canUndoChanged.emit(self.canUndo())

    def redo(self, branch=None):
        old_can_redo = self.canRedo()
        try:
            self._disableUndo = True
            self._currentUndoAction.redoStep(branch)
            new_modified = self._currentUndoAction.wasModified
        finally:
            self._disableUndo = False
        self.isModified = new_modified
        if old_can_redo != self.canRedo():
            self.canRedoChanged.emit(self.canRedo())

    def canUndo(self):
        return self._currentUndoAction.canUndo()

    def canRedo(self):
        return self._currentUndoAction.canRedo()

    def alternativeBranches(self):
        return self._currentUndoAction.alternativeBranches()

    @property
    def canQuickSave(self):
        return self._canQuickSave

    def save(self, device=None, switch_device=False):
        """Completely writes all editor data into given device.
        """
        with self.lock:
            if device is None:
                if not self.isModified:
                    return
                device = self.device

            if device is None:
                raise ValueError('device is None')

            saver = self.device.createSaver(self, device)
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
                    self._currentSavepointIndex += 1
                self.isModified = False

                if switch_device:
                    for span in self._spans:
                        if isinstance(span, DeviceSpan) and span._device is self._device:
                            span._device = device

                    self._device = device
                    self.urlChanged.emit(self.url)


class AbstractUndoAction(object):
    def __init__(self, editor, title=''):
        self.title = title
        self.editor = editor
        self.parent = None
        self._wasModified = editor.isModified
        self._savepointIndex = editor._currentSavepointIndex

    def _restore(self):
        self.editor.isModified = self._wasModified
        self.editor._currentSavepointIndex = self._savepointIndex

    def undo(self):
        self._restore()

    def redo(self):
        self._restore()


class InsertAction(AbstractUndoAction):
    def __init__(self, editor, position, spans, title=''):
        if not title:
            title = utils.tr('insert {0} bytes from position {1}'.format(editor._calculateSpansLength(spans), position))
        AbstractUndoAction.__init__(self, editor, title)
        self.spans = spans
        self.position = position

    def undo(self):
        # just remove inserted spans...
        self.editor.removeSpans(self.position, len(self.spans))
        AbstractUndoAction.undo(self)

    def redo(self):
        self.editor.insertSpans(self.position, self.spans)
        AbstractUndoAction.redo(self)


class RemoveAction(AbstractUndoAction):
    def __init__(self, editor, position, spans, title=''):
        if not title:
            title = utils.tr('remove {0} bytes from position {1}'.format(editor._calculateSpansLength(spans), position))
        AbstractUndoAction.__init__(self, editor, title)
        self.spans = spans
        self.position = position

    def undo(self):
        # insert them back
        self.editor.insertSpans(self.position, self.spans)
        AbstractUndoAction.undo(self)

    def redo(self):
        self.editor.removeSpans(self.position, len(self.spans))
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

