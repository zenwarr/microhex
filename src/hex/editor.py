import copy
import threading
from PyQt4.QtCore import pyqtSignal, QObject


class OutOfBoundsError(ValueError):
    def __init__(self):
        ValueError.__init__(self, 'position is out of bounds')


class Span(object):
    """Span controls piece of immutable data. Spans are immutable and thread-safe so
    data span controls should be immutable too.
    Span has parent that identifies Editor this span created for.
    Each Span should support read and split methods. 'read' method returns bytes object with given data.
    """
    NoFlag = 0
    Native = 1

    def __init__(self, parent=None, flags=NoFlag):
        self.__parent = parent
        self.__flags = flags
        self.__lock = threading.RLock()

    @property
    def lock(self):
        return self.__lock

    @property
    def parent(self):
        with self.lock:
            return self.__parent

    @property
    def flags(self):
        with self.lock:
            return self.__flags

    @property
    def length(self):
        raise NotImplementedError()

    def read(self, offset, size):
        raise NotImplementedError()

    def split(self, offset):
        with self.lock:
            if offset < 0 or offset >= len(self):
                raise OutOfBoundsError()
            return copy.deepcopy(self), copy.deepcopy(self)

    def clone(self, new_parent):
        cloned = copy.deepcopy(self)
        cloned.__parent = new_parent
        return cloned

    def __len__(self):
        return self.length

    def __ne__(self, other):
        return not (self == other)

    def isRangeValid(self, offset, size):
        return 0 <= offset and 0 <= size and offset + size <= self.length


class DataSpan(Span):
    def __init__(self, parent, data, flags=Span.NoFlag):
        Span.__init__(self, parent, flags)
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
            return (f, s)

    def __deepcopy__(self, memo):
        with self.lock:
            return DataSpan(self.parent, self.__data, self.flags)

    def __eq__(self, other):
        if not isinstance(other, DataSpan):
            return NotImplemented
        return self.__data == other.__data


class DeviceSpan(Span):
    def __init__(self, parent, device, device_offset, device_len, flags=Span.NoFlag):
        Span.__init__(self, parent, flags)
        if device_offset < 0:
            raise ValueError('invalid arguments')
        self.__device = device
        self.__deviceOffset = device_offset
        self.__deviceLen = device_len if device_len >= 0 else -1

    @property
    def length(self):
        with self.lock:
            if self.__deviceLen >= 0:
                return self.__deviceLen
            else:
                size = len(self.__device) - self.__deviceOffset
                return size if size >= 0 else 0

    def read(self, offset, size):
        with self.lock:
            if not self.isRangeValid(offset, size):
                raise OutOfBoundsError()
            if self.__device is None:
                return bytes()
            with self.__device.lock:
                device_length = self.length
                if device_length >= 0:
                    self.__device.seek(self.__deviceOffset + offset)
                    return self.__device.read(size)
                else:
                    return bytes()

    def split(self, offset):
        f, s = Span.split(self, offset)
        f.__deviceLen = offset
        s.__deviceOffset = self.__deviceOffset + offset
        s.__deviceLen = len(self) - offset if self.__deviceLen >= 0 else -1
        return f, s

    def __deepcopy__(self, memo):
        with self.lock:
            return DeviceSpan(self.parent, self.__device, self.__deviceOffset, self.__deviceLen, self.flags)

    def __eq__(self, other):
        if not isinstance(other, DeviceSpan):
            return NotImplemented
        return self.__device is other.__device and self.__deviceOffset == other.__deviceOffset and \
                    self.__deviceLen == other.__deviceLen


class FillSpan(Span):
    def __init__(self, parent, pattern, length, flags=Span.NoFlag):
        Span.__init__(self, parent, flags)
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
        return s, f

    def __deepcopy__(self, memo):
        with self.lock:
            return FillSpan(self.parent, self.__pattern, self.__length, self.flags)

    def __eq__(self, other):
        if not isinstance(other, FillSpan):
            return NotImplemented
        return self.__pattern == other.__pattern and self.__length == other.__length


class Editor(QObject):
    dataChanged = pyqtSignal(int, int)
    resized = pyqtSignal(int)

    def __init__(self, device=None):
        QObject.__init__(self)
        self.__device = device
        self.__lock = threading.RLock()
        self.__modified = False
        self.__totalLength = 0
        self.__spans = []

        if self.__device:
            # initialize editor with one span referencing all device data
            self.__spans.append(DeviceSpan(self, self.__device, 0, -1, Span.Native))
            self.__totalLength = len(self.__device)

    @property
    def lock(self):
        return self.__lock

    @property
    def device(self):
        return self.__device

    @property
    def length(self):
        with self.lock:
            return self.__totalLength

    def read(self, position, length):
        """Reads data at :position:. Fails with OutOfBoundsError if there less than :length: bytes after :position:
        """

        with self.lock:
            if position < 0 or length < 0 or position + length > len(self):
                raise OutOfBoundsError()
            spans, left_offset, right_offset = self.spansInRange(position, length)
            result = bytes()
            for span_index in range(len(spans)):
                pos = left_offset if span_index == 0 else 0
                size = (right_offset - left_offset) + 1 if span_index == len(spans) - 1 else len(spans[span_index])
                result += spans[span_index].read(pos, size)
            return result

    def readAtEnd(self, position, length):
        """Reads data at :position:, but unlike Editor.read, does not fails when no :length: bytes can be read. It
        reads as much data as possible but maximal :length: bytes
        """

        with self.lock:
            if position < 0 or length < 0 or position >= len(self):
                raise OutOfBoundsError()
            if position + length > len(self):
                length = len(self) - position
            return self.read(position, length)

    def readAll(self):
        """Read all data from editor."""

        with self.lock:
            result = bytes()
            for span in self.spans:
                result += span.read(0, len(span))
            return result

    @property
    def spans(self):
        """List of all spans in editor"""

        with self.lock:
            return self.__spans

    def spanAtPosition(self, position):
        """Get span that holds byte at :position:.
        """

        with self.lock:
            span_index = self.__findSpanIndex(position)[0]
            return self.__spans[span_index] if span_index >= 0 else None

    def spansInRange(self, position, length):
        """Get list of spans in given range. Returns tuple (spans, left_offset, right_offset).
        First and last span boundaries can be not exactly (position, position + length - 1).
        If range is out of editor size, empty list will be returned.
        First span in returned list always holds byte at :position: and last span holds byte at :position: + :length: - 1
        """

        with self.lock:
            if position < 0 or length < 0 or position + length > len(self):
                raise OutOfBoundsError()

            if not self.__spans:
                return [], 0, 0

            first_span_index, left_offset = self.__findSpanIndex(position)
            last_span_index, right_offset = self.__findSpanIndex(position + length - 1)
            if first_span_index < 0:
                return [], 0, 0
            if last_span_index < 0:
                last_span_index = len(self.__spans) - 1
            return self.__spans[first_span_index:last_span_index+1], left_offset, right_offset

    def takeSpans(self, position, length):
        """Same as Editor.spansInRange, but first splits spans at boundaries, so first span always starts with byte
        at :position: and last one always ends with byte at :position: + :length: - 1
        """

        with self.lock:
            if position < 0 or length < 0 or position + length >= len(self):
                raise OutOfBoundsError()

            if not self.__spans:
                return []
            self.splitSpans(position)
            self.splitSpans(position + length)
            return self.spansInRange(position, length)

    def insertSpan(self, position, span):
        self.insertSpans(position, [span])

    def insertSpans(self, position, spans):
        """Insert spans before byte at given position. Will fail if position == len(self)"""

        with self.lock:
            if position < 0 or position >= len(self):
                raise OutOfBoundsError()
            if spans:
                self.splitSpans(position)
                span_index = self.__findSpanIndex(position)[0]
                for span in spans:
                    cloned_span = span.clone(self)
                    self.__spans.insert(span_index, cloned_span)
                    span_index += 1
                    self.__totalLength += len(cloned_span)
                self.__modified = True
                self.dataChanged.emit(position, -1)
                self.resized.emit(len(self))

    def appendSpan(self, span):
        self.appendSpans([span])

    def appendSpans(self, spans):
        """Append span to the end of spans list"""

        old_length = len(self)
        for span in spans:
            cloned_span = span.clone(self)
            self.__spans.append(cloned_span)
            self.__totalLength += len(cloned_span)
        self.__modified = True
        self.dataChanged.emit(old_length, -1)
        self.resized.emit(len(self))

    def writeSpan(self, position, span):
        self.writeSpans(position, [span])

    def writeSpans(self, position, spans):
        """Writes spans at :position:
        """

        if position < 0:
            raise OutOfBoundsError()

        length = Editor.__calculateSpansLength(spans)
        if position < len(self):
            self.splitSpans(position)
            self.splitSpans(position + length)

            first_span_index = self.__findSpanIndex(position)[0]
            del self.__spans[first_span_index:self.__findSpanIndex(position + length - 1)[0] + 1]

            span_index = first_span_index
            for span in spans:
                cloned_span = span.clone(self)
                self.__spans.insert(span_index, cloned_span)
                span_index += 1

            self.__modified = True
            self.dataChanged.emit(position, length)
        elif position == len(self):
            self.appendSpans(spans)
        else:
            self.appendSpan(FillSpan(self, b'\0', position - len(self)))
            self.appendSpans(spans)

    def remove(self, position, length):
        if position < 0 or length < 0 or position >= len(self):
            raise OutOfBoundsError()
        if position + length >= len(self):
            length = len(self) - position

        self.splitSpans(position)
        self.splitSpans(position + length)

        first_span_index = self.__findSpanIndex(position)[0]
        last_span_index = self.__findSpanIndex(position + length - 1)[0] + 1

        del self.__spans[first_span_index:last_span_index]
        self.__totalLength -= length
        self.__modified = True

        self.dataChanged.emit(position, -1)
        self.resized.emit(len(self))

    @property
    def isModified(self):
        return self.__modified

    def isRangeModified(self, position, length=1):
        if not self.__modified:
            return False
        return any(not (s.flags & Span.Native) for s in self.spansInRange(position, length)[0])

    def undo(self):
        pass

    def redo(self):
        pass

    def canUndo(self):
        pass

    def canRedo(self):
        pass

    def __len__(self):
        with self.lock:
            return self.__totalLength

    def __findSpanIndex(self, position):
        """Find span byte with given position is located in
        """
        if not self.__spans or position < 0 or position >= len(self):
            return -1, 0

        cpos = 0
        for span_index in range(len(self.__spans)):
            span = self.__spans[span_index]
            if position >= cpos and position < cpos + len(span):
                return span_index, position - cpos
            cpos += len(span)
        else:
            return -1, 0

    def splitSpans(self, position):
        """Ensure that byte with given position is first byte in span. If not, split span with this byte into two.
        """
        span_index, offset = self.__findSpanIndex(position)
        if span_index >= 0 and offset != 0:
            span = self.__spans[span_index]
            splitted = span.split(offset)

            del self.__spans[span_index]
            self.__spans.insert(span_index, splitted[1])
            self.__spans.insert(span_index, splitted[0])

    @staticmethod
    def __calculateSpansLength(spans):
        result = 0
        for span in spans:
            result += len(span)
        return result

    def clear(self):
        with self.lock:
            if self.__spans:
                self.__spans = []
                self.__totalLength = 0
                self.dataChanged.emit(0, -1)
                self.resized.emit(0)

    def bytesRange(self, range_start, range_end):
        """Allows iterating over bytes in given range"""
        for position in range(range_start, range_end):
            try:
                yield self.read(position, 1)
            except OutOfBoundsError:
                break
