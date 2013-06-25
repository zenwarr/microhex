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
        return 255 ** self.dataSize

    @property
    def minimal(self):
        return -self.maximal if self.signed else 0

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
        FormatFloat: 4,
        FormatDouble: 8
    }

    def __init__(self, binary_format, endianess=LittleEndian):
        GenericCodec.__init__(self)
        self.binaryFormat = binary_format
        self.endianess = endianess
        self.dataSize = self._t.get(binary_format)

    @property
    def formatString(self):
        return self.endianess + self.binaryFormat
