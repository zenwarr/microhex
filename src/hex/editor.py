import copy
import contextlib
import weakref
from PyQt4.QtCore import pyqtSignal, QObject, QByteArray
import hex.utils as utils
import hex.operations as operations


class EditorError(IOError):
    pass


class OutOfBoundsError(EditorError):
    def __init__(self):
        EditorError.__init__(self, 'position is out of bounds')


class ReadOnlyError(EditorError):
    def __init__(self):
        EditorError.__init__(self, utils.tr('operation not allowed for editor in read-only mode'))


class FreezeSizeError(EditorError):
    def __init__(self):
        EditorError.__init__(self, utils.tr('operation is not allowed for editor with frozen size'))


DefaultFillPattern = b'\0'


class Span(object):
    """Span controls piece of immutable data. Spans are immutable and not thread-safe."""
    def __init__(self, parent=None):
        self._parent = parent
        self.savepoint = -1
        self.parentChain = None

    @property
    def parent(self):
        return self._parent

    @property
    def length(self):
        raise NotImplementedError()

    def read(self, offset, size):
        raise NotImplementedError()

    def split(self, offset):
        if not 0 <= offset < len(self):
            raise OutOfBoundsError()
        return self.clone(self.parent), self.clone(self.parent)

    def clone(self, new_parent):
        cloned = copy.deepcopy(self)
        cloned._parent = new_parent
        return cloned

    def __len__(self):
        return self.length

    def isRangeValid(self, offset, size):
        return 0 <= offset and 0 <= size and offset + size <= self.length

    def byteRange(self, offset, size):
        raise NotImplementedError()


class DataSpan(Span):
    def __init__(self, parent, data):
        Span.__init__(self, parent)
        self._data = bytes(data)
        self._length = len(self._data)

    @property
    def length(self):
        return self._length

    def read(self, offset, size):
        if not self.isRangeValid(offset, size):
            raise OutOfBoundsError()
        return self._data[offset:offset+size]

    def split(self, offset):
        f, s = Span.split(self, offset)
        f._data = self._data[:offset]
        f._length = offset
        s._data = self._data[offset:]
        s._length = self._length - offset
        return f, s

    def __deepcopy__(self, memo):
        cloned = DataSpan(self.parent, self._data)
        cloned.savepoint = self.savepoint
        return cloned

    def __eq__(self, other):
        if not isinstance(other, DataSpan):
            return NotImplemented
        return self._data == other._data

    def byteRange(self, offset, size):
        if not self.isRangeValid(offset, size):
            raise OutOfBoundsError()
        yield from self._data[offset:offset + size]


class DeviceSpan(Span):
    def __init__(self, parent, device, device_offset, device_len):
        Span.__init__(self, parent)
        self._device = device
        self.deviceOffset = device_offset
        self.deviceLen = device_len if device_len >= 0 else -1
        self._dissolvingTo = None
        self._dissolvingToDevice = None
        self._device._addSpan(self)

    @property
    def device(self):
        return self._device

    @device.setter
    def device(self, new_device):
        if self._device is not new_device:
            self._device._removeSpan(self)
            self._device = new_device
            self._device._addSpan(self)

    @property
    def length(self):
        return self.deviceLen

    def read(self, offset, size):
        if not self.isRangeValid(offset, size):
            raise OutOfBoundsError()
        if self._device is None:
            return bytes()
        return self._device.read(self.deviceOffset + offset, size)

    def split(self, offset):
        f, s = Span.split(self, offset)
        f.deviceLen = offset
        s.deviceOffset = self.deviceOffset + offset
        s.deviceLen = len(self) - offset if self.deviceLen >= 0 else -1
        if self._dissolvingTo is not None:
            f._dissolvingTo = copy.deepcopy(self._dissolvingTo.takeSpans(0, offset))
            f._dissolvingToDevice = self._dissolvingToDevice
            s._dissolvingTo = copy.deepcopy(self._dissolvingTo.takeSpans(offset, self.deviceLen - offset))
            s._dissolvingToDevice = self._dissolvingToDevice
        return f, s

    def __deepcopy__(self, memo):
        cloned = DeviceSpan(self.parent, self._device, self.deviceOffset, self.deviceLen)
        cloned.savepoint = self.savepoint
        cloned._dissolvingTo = self._dissolvingTo
        cloned._dissolvingToDevice = self._dissolvingToDevice
        return cloned

    def __eq__(self, other):
        if not isinstance(other, DeviceSpan):
            return NotImplemented
        return (self._device is other._device and self.deviceOffset == other.deviceOffset and
                self.deviceLen == other.deviceLen)

    def prepareToDissolve(self, new_device, replacement):
        self._dissolvingTo = replacement
        self._dissolvingToDevice = new_device

    def cancelDissolving(self):
        self._dissolvingTo = None

    def dissolve(self):
        if self._dissolvingTo is not None:
            for span in self._dissolvingTo:
                if isinstance(span, DeviceSpan):
                    span._device = self._dissolvingToDevice
            self.parentChain.dissolveSpan(self, self._dissolvingTo)

    def __hash__(self):
        return hash('{0};{1}'.format(self.deviceOffset, self.deviceLen))

    def byteRange(self, offset, size):
        if not self.isRangeValid(offset, size):
            raise OutOfBoundsError()
        yield from self._device.byteRange(self.deviceOffset + offset, size)


class FillSpan(Span):
    def __init__(self, parent, pattern, repeat_count):
        Span.__init__(self, parent)
        self._pattern = bytes(pattern)
        self._repeatCount = repeat_count
        self._length = len(self._pattern) * repeat_count

    @property
    def length(self):
        return self._length

    def read(self, offset, size):
        if not self.isRangeValid(offset, size):
            raise OutOfBoundsError()
        rem = size % len(self._pattern)
        return self._pattern * (size // len(self._pattern)) + self._pattern[:rem]

    def split(self, offset):
        f, s = Span.split(self, offset)
        f._length = offset
        s._length = self._length - offset
        return f, s

    def __deepcopy__(self, memo):
        cloned = FillSpan(self.parent, self._pattern, self._length)
        cloned.savepoint = self.savepoint
        return cloned

    def __eq__(self, other):
        if not isinstance(other, FillSpan):
            return NotImplemented
        return self._pattern == other._pattern and self._length == other._length

    def byteRange(self, offset, size):
        if not self.isRangeValid(offset, size):
            raise OutOfBoundsError()
        for byte_index in range(offset, offset + size):
            yield self._pattern[byte_index // len(self._pattern)]


class SpanChain(object):
    """Class represents non-constant chain of spans."""
    def __init__(self, spans=None):
        self._spans = []
        self._length = 0
        if spans:
            self.spans = spans

    @property
    def spans(self):
        return self._spans

    @spans.setter
    def spans(self, spans):
        self._spans = copy.deepcopy(spans)
        for span in self._spans:
            span.parentChain = self
        self._length = self._calculateLength(self._spans)

    def __len__(self):
        return self._length

    def clear(self):
        self.spans = []

    @staticmethod
    def _calculateLength(span_list):
        return sum(span.length for span in span_list)

    def _spanReadIterator(self, offset, size):
        if offset < 0 or size < 0:
            raise OutOfBoundsError()
        elif offset < self._length and offset + size > self._length:
            size = self._length - offset
        elif offset >= self._length:
            return

        spans, left_offset, right_offset = self.spansInRange(offset, size)
        for span_index in range(len(spans)):
            pos = left_offset if span_index == 0 else 0
            size = (right_offset - pos) + 1 if span_index == len(spans) - 1 else len(spans[span_index]) - pos
            yield spans[span_index], pos, size

    def read(self, offset, size):
        result = b''
        for span, offset, size in self._spanReadIterator(offset, size):
            result += span.read(offset, size)
        return result

    def byteRange(self, offset, size):
        for span, offset, size in self._spanReadIterator(offset, size):
            yield from span.byteRange(offset, size)

    def spansInRange(self, offset, size):
        if offset < 0 or size < 0:
            raise OutOfBoundsError()
        elif offset + size > self._length:
            size = self._length - offset

        if not self._spans or size <= 0:
            return [], 0, 0

        first_span_index, left_offset = self.findSpanIndex(offset)
        last_span_index, right_offset = self.findSpanIndex(offset + size - 1)
        assert(first_span_index >= 0 and last_span_index >= 0)
        return self._spans[first_span_index:last_span_index+1], left_offset, right_offset

    def findSpanIndex(self, offset):
        if not self._spans or offset < 0 or offset >= self._length:
            return -1, 0

        current_offset = 0
        for span_index in range(len(self._spans)):
            span = self._spans[span_index]
            if current_offset <= offset < current_offset + span.length:
                return span_index, offset - current_offset
            current_offset += span.length
        else:
            return -1, 0

    def spanAtOffset(self, offset):
        span_index = self.findSpanIndex(offset)[0]
        return self._spans[span_index] if span_index >= 0 else None

    def takeSpans(self, offset, size):
        if offset < 0 or size < 0:
            raise OutOfBoundsError()
        elif offset >= self._length:
            return []
        elif offset + size > self._length:
            size = self._length - offset

        if not self._spans or size <= 0:
            return []

        self.splitSpans(offset)
        self.splitSpans(offset + size)
        return self.spansInRange(offset, size)[0]

    def splitSpans(self, offset):
        span_index, offset = self.findSpanIndex(offset)
        if span_index >= 0 and offset != 0:
            span = self._spans[span_index]

            splitted = span.split(offset)
            splitted[0].parentChain = self
            splitted[1].parentChain = self
            self._spans[span_index:span_index + 1] = splitted

    def insertChain(self, offset, chain):
        if 0 <= offset < self._length:
            self.splitSpans(offset)
            span_index = self.findSpanIndex(offset)[0]
        elif offset == self._length:
            span_index = len(self._spans)
        else:
            raise OutOfBoundsError()

        spans_to_insert = copy.deepcopy(chain.spans)
        for span in spans_to_insert:
            span.parentChain = self

        self._spans[span_index:span_index] = spans_to_insert
        self._length += len(chain)

    def remove(self, offset, length):
        if not 0 <= offset < len(self):
            raise OutOfBoundsError()

        removed_spans = self.takeSpans(offset, length)
        first_span_index = self.findSpanIndex(offset)[0]
        last_span_index = first_span_index + len(removed_spans)
        del self._spans[first_span_index:last_span_index]
        self._length -= length
        return removed_spans

    def dissolveSpan(self, span, replacement):
        assert isinstance(replacement, list) and self._calculateLength(replacement) == len(span)
        for span_index in range(len(self._spans)):
            if self._spans[span_index] is span:
                replacement = copy.deepcopy(replacement)
                for rep_span in replacement:
                    rep_span.parentChain = self
                self._spans[span_index:span_index+1] = replacement
                break


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
        self._spanChain = SpanChain()
        self._currentUndoAction = None
        self._disableUndo = False
        self._freezeSize = device.fixedSize
        self._readOnly = device.readOnly
        self._currentAtomicOperationIndex = 0
        self._savepoint = 0

        if len(self._device):
            # initialize editor chain with one span referencing all device data
            self._spanChain.spans = [DeviceSpan(self, self._device, 0, len(self._device))]
            self._spanChain.spans[0].savepoint = 0

        self._currentUndoAction = ComplexAction(self, utils.tr('initial state'))
        self._device.urlChanged.connect(self.urlChanged)

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
        return len(self._spanChain)

    def __len__(self):
        return len(self._spanChain)

    @property
    def fixedSize(self):
        return self._freezeSize

    @fixedSize.setter
    def fixedSize(self, new_freeze):
        with self.lock.write:
            if not new_freeze and self._device.fixedSize:
                raise EditorError('failed to turn fixed size mode off for device with fixed size')
            self._freezeSize = new_freeze

    @property
    def readOnly(self):
        return self._readOnly

    @readOnly.setter
    def readOnly(self, new_read_only):
        with self.lock.write:
            if not new_read_only and self._device.readOnly:
                raise EditorError('failed to turn read only mode off for read only device')
            self._readOnly = new_read_only

    def read(self, position, length):
        """Reads as much data as possible (but not more than :length: bytes) starting from :position:"""
        with self.lock.read:
            return self._spanChain.read(position, length)

    def readAll(self):
        with self.lock.read:
            return self.read(0, self.length)

    def insertSpan(self, position, span, fill_pattern=DefaultFillPattern):
        """Shorthand method for Editor.insertSpanChain"""
        self.insertSpanChain(position, SpanChain([span]), fill_pattern)

    def insertSpanChain(self, position, chain, fill_pattern=DefaultFillPattern, undo=False):
        """Insert list of spans into given :position:. After inserting, first byte of first span in list will have
        :position: index in editor. If :position: > self.length, space between end of editor data and insertion point
        will be occupied by FillSpan initialized by :fill_pattern:. If :fill_pattern: is None, method will raise
        OutOfBoundsError if :position: > self.length.
        Raises OutOfBoundsError is :position: is negative.
        """

        with self.lock.write:
            if self._readOnly:
                raise ReadOnlyError()
            if self._freezeSize:
                raise FreezeSizeError()

            self._insertSpanChain(position, chain, fill_pattern, undo)

            if len(chain):
                self.resized.emit(len(self))
                self.bytesInserted.emit(position, len(chain))
                self.dataChanged.emit(min(len(self) - len(chain), position), -1)

    def _insertSpanChain(self, position, chain, fill_pattern=DefaultFillPattern, undo=False):
        if position < 0 or (fill_pattern is None and position > len(self)):
            raise OutOfBoundsError()

        if position > len(self):
            chain.spans = [FillSpan(self, fill_pattern, position - len(self))] + chain.spans
            position = len(self._spanChain)
        self._spanChain.insertChain(position, chain)

        if not undo:
            self.addAction(InsertAction(self, position, SpanChain(chain.spans)))
        self._incrementAtomicOperationIndex(-1 if undo else 1)

    def appendSpan(self, span):
        """Shorthand method for Editor.insertSpan
        """
        with self.lock.write:
            self.insertSpan(len(self), span)

    def appendSpanChain(self, chain):
        """Shorthand method for Editor.insertSpanChain
        """
        with self.lock.write:
            self.insertSpanChain(len(self), chain)

    def writeSpan(self, position, span, fill_pattern=DefaultFillPattern):
        """Shorthand method for Editor.writeSpanChain
        """
        self.writeSpanChain(position, SpanChain([span]), fill_pattern)

    def writeSpanChain(self, position, chain, fill_pattern=DefaultFillPattern):
        """Overwrites data starting from :position: with given SpanChain.
        If position is out of editor data, editor will be resized, and space between old end of data and write position
        will be occupied by FillSpan initialized with :fill_pattern:. If :fill_pattern: is None, raises OutOfBoundsError
        if :position: > self.length. Raises OutOfBoundsError if position < 0.
        """

        with self.lock.write:
            if self._readOnly:
                raise ReadOnlyError()
            if position < 0:
                raise OutOfBoundsError()
            if self.fixedSize and position + len(chain) > len(self):
                raise FreezeSizeError()

            old_length = len(self)

            try:
                self.beginComplexAction(utils.tr('writing {0} bytes at position {1}').format(len(chain), position))
                if position < len(self):
                    self._remove(position, len(chain))
                self._insertSpanChain(position, chain, fill_pattern)
            finally:
                self.endComplexAction()

            if len(chain):
                self.resized.emit(len(self))
                self.dataChanged.emit(min(position, old_length), -1)
            else:
                self.dataChanged.emit(position, len(chain))

    def _remove(self, position, length, undo=False):
        if position < 0:
            raise OutOfBoundsError()
        if not len(self) or length <= 0 or position >= len(self):
            return
        if position + length >= len(self):
            length = len(self) - position

        removed_spans = self._spanChain.remove(position, length)

        if not undo:
            self.addAction(RemoveAction(self, position, SpanChain(removed_spans)))
        self._incrementAtomicOperationIndex(-1 if undo else 1)

    def remove(self, position, length, undo=False):
        """Remove :length: bytes starting from byte with index :position:. If length < 0, removes all bytes from
        :position: until end. If less then :length: bytes available, also removes all bytes until end.
        Raises OutOfBoundsError if position is negative or :position: >= self.length.
        """

        with self.lock.write:
            if self._readOnly:
                raise ReadOnlyError()
            if self.fixedSize and length != 0:
                raise FreezeSizeError()

            self._remove(position, length, undo)

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
            if not self.isModified or position >= len(self):
                return False
            elif position + length >= len(self):
                length = len(self) - position
            return any(span.savepoint != self._savepoint for span in self._spanChain.spansInRange(position, length)[0])

    def clear(self):
        with self.lock.write:
            if len(self):
                self._spanChain.clear()
                self.dataChanged.emit(0, -1)
                self.resized.emit(0)

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

    def save(self, write_device=None, switch_device=False):
        """Completely writes all editor data into given device.
        """
        with self.lock.write:
            if write_device is None:
                if not self.isModified:
                    return
                write_device = self.device

            if write_device is None:
                raise ValueError('device is None')
            read_device = self._device

            saver = write_device.createSaver(self, self.device)

            if read_device is write_device or switch_device:
                self._prepareToUpdateDevice(self._device if not switch_device else write_device)

            saver.begin()
            try:
                for span in self._spanChain.spans:
                    saver.putSpan(span)
            except:
                saver.fail()
                for span in self._deviceSpans:
                    span.cancelDissolve()
                raise
            else:
                saver.complete()

                if switch_device:
                    self._device = write_device

                if switch_device or read_device is write_device:
                    # now save changes we have made in spans. Make all device spans in chain reference our device.
                    current_position = 0
                    for span in self._spanChain.spans:
                        if isinstance(span, DeviceSpan):
                            span._device = self._device
                            span.deviceOffset = current_position
                        current_position += len(span)

                    for device_span in write_device._spans:
                        device_span.dissolve()

                self._setSavepoint()

                if switch_device:
                    self.urlChanged.emit(self.url)

    def _prepareToUpdateDevice(self, new_device):
        # assign temporary 'cposition' attribute to all spans that will be in saved device
        current_position = 0
        for span in self._spanChain.spans:
            span.cposition = current_position
            current_position += len(span)

        alive_spans = [span for span in self._spanChain.spans if isinstance(span, DeviceSpan) and span._device is self._device]

        spans_to_dissolve = [span for span in self._device._spans if span.parentChain is not self._spanChain]
        for span in spans_to_dissolve:
            # now try to find alive spans that has same data as this device holds
            replacement = []
            dev_position = span.deviceOffset
            while dev_position < span.deviceOffset + span.deviceLen:
                hitted = [span for span in alive_spans
                          if span.deviceOffset <= dev_position < span.deviceOffset + span.deviceLen]
                if not hitted:
                    # find closest span...
                    closest = None
                    try:
                        closest = min((span for span in alive_spans if span.deviceOffset > dev_position),
                                      key=lambda x: x.deviceOffset - dev_position)
                    except ValueError:
                        pass

                    if closest is None or closest.deviceOffset >= span.deviceOffset + span.deviceLen:
                        size = span.deviceLen - (dev_position - span.deviceOffset)
                    else:
                        size = closest.deviceOffset - dev_position

                    # replace with data span...
                    try:
                        replacement.append(DataSpan(self, self._device.read(dev_position, size)))
                    except MemoryError:
                        raise EditorError('failed to convert to DataSpan: not enough memory')

                    dev_position += size
                else:
                    chosen = max(hitted, key=lambda x: x.deviceOffset + x.deviceLen - dev_position)
                    offset = dev_position - chosen.deviceOffset
                    replacement.append(DeviceSpan(self, self._device, chosen.cposition + offset,
                                                  chosen.deviceLen - offset))
                    dev_position = chosen.deviceOffset + chosen.deviceLen
            span.prepareToDissolve(new_device, replacement)

    def _setSavepoint(self):
        if self._savepoint != self._currentAtomicOperationIndex:
            self._savepoint = self._currentAtomicOperationIndex
            for span in self._spanChain._spans:
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

    def checkCanQuickSave(self):
        current_position = 0
        for span in self._spanChain.spans:
            if isinstance(span, DeviceSpan) and span.deviceOffset != current_position:
                return False
            current_position += len(span)
        return True

    def byteRange(self, position, length):
        with self.lock.read:
            yield from self._spanChain.byteRange(position, length)


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
    def __init__(self, editor, position, chain, title=''):
        if not title:
            title = utils.tr('insert {0} bytes from position {1}'.format(len(chain), position))
        AbstractUndoAction.__init__(self, editor, title)
        self.chain = chain
        self.position = position

    def undo(self):
        # just remove inserted spans...
        self.editor.remove(self.position, len(self.chain), undo=True)
        AbstractUndoAction.undo(self)

    def redo(self):
        self.editor.insertSpanChain(self.position, self.chain)
        AbstractUndoAction.redo(self)


class RemoveAction(AbstractUndoAction):
    def __init__(self, editor, position, chain, title=''):
        if not title:
            title = utils.tr('remove {0} bytes from position {1}'.format(len(chain), position))
        AbstractUndoAction.__init__(self, editor, title)
        self.chain = chain
        self.position = position

    def undo(self):
        # insert them back
        self.editor.insertSpanChain(self.position, self.chain, undo=True)
        AbstractUndoAction.undo(self)

    def redo(self):
        self.editor.remove(self.position, len(self.chain))
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
