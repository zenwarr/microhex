import struct
import hex.utils as utils


LittleEndian = '<'
BigEndian = '>'


class GenericCodec(object):
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
        Format8Bit: (1, utils.tr('Byte')),
        Format16Bit: (2, utils.tr('Word')),
        Format32Bit: (4, utils.tr('Double word')),
        Format64Bit: (8, utils.tr('Quad word'))
    }

    def __init__(self, binary_format=Format8Bit, signed=True, endianess=LittleEndian):
        GenericCodec.__init__(self)
        self.binaryFormat = binary_format
        self.signed = signed
        self.endianess = endianess

    @property
    def maximal(self):
        return (256 ** self.dataSize // (2 if self.signed else 1)) - 1

    @property
    def minimal(self):
        return -self.maximal - 1 if self.signed else 0

    @staticmethod
    def formatName(fmt):
        return IntegerCodec._t[fmt][1]

    @property
    def formatString(self):
        return self.endianess + (self.binaryFormat if self.signed else self.binaryFormat.upper())

    @property
    def dataSize(self):
        return self._t.get(self.binaryFormat)[0]


class FloatCodec(GenericCodec):
    FormatFloat = 'f'
    FormatDouble = 'd'

    _t = {
        FormatFloat: (4, utils.tr('32-bit float')),
        FormatDouble: (8, utils.tr('64-bit float'))
    }

    def __init__(self, binary_format=FormatFloat, endianess=LittleEndian):
        GenericCodec.__init__(self)
        self.binaryFormat = binary_format
        self.endianess = endianess

    @property
    def formatString(self):
        return self.endianess + self.binaryFormat

    @property
    def dataSize(self):
        return self._t.get(self.binaryFormat)[0]

    @staticmethod
    def formatName(fmt):
        return FloatCodec._t.get(fmt)[1]
