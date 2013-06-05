from PyQt4.QtCore import QObject, pyqtSignal
import struct


LittleEndian = '<'
BigEndian = '>'


class GenericCodec(object):
    def __init__(self, format_string):
        self.formatString = format_string

    def decode(self, data):
        unpacked = struct.unpack(self.formatString, data)
        return unpacked[0] if unpacked else None

    def encode(self, value):
        return struct.pack(self.formatString, value)


class IntegerCodec(GenericCodec):
    Format8Bit = 'b'
    Format16Bit = 'h'
    Format32Bit = 'i'
    Format64Bit = 'q'

    _t = {
        Format8Bit: 1,
        Format16Bit: 2,
        Format32Bit: 4,
        Format64Bit: 8
    }

    def __init__(self, binary_format, signed=True, endianess=LittleEndian):
        GenericCodec.__init__(self, endianess + (binary_format if signed else binary_format.upper()))
        self.binaryFormat = binary_format
        self.signed = signed
        self.endianess = endianess
        self.dataSize = self._t.get(self.binaryFormat)


class FloatCodec(GenericCodec):
    FormatFloat = 'f'
    FormatDouble = 'd'

    _t = {
        FormatFloat: 4,
        FormatDouble: 8
    }

    def __init__(self, binary_format, endianess=LittleEndian):
        GenericCodec.__init__(self, endianess + binary_format)
        self.binaryFormat = binary_format
        self.endianess = endianess
        self.dataSize = self._t.get(binary_format)
