from PyQt4.QtCore import QTextCodec
import hex.utils as utils


class EncodingError(ValueError):
    pass


class PartialCharacterError(EncodingError):
    def __init__(self, desc=''):
        EncodingError.__init__(self, utils.tr('only part of character is available - {0}').format(desc))


class CharacterData(object):
    def __init__(self):
        self.unicode = ''
        self.document = None
        self.startPosition = -1
        self.bytesCount = -1
        self.documentData = b''


class AbstractCodec(object):
    def __init__(self, name):
        self.name = name

    @property
    def fixedSize(self):
        """Returns number of bytes occupied by one character if encoding is fixed-width. Should return -1 for
        variable-width encodings.
        """
        raise NotImplementedError()

    @property
    def canDetermineCharacterStart(self):
        """Returns True if codec can determine where character starts by any byte of this character. For example,
        for utf-8 encoding this property should return True, and False for utf-16 or utf-32 encodings. Note that
        this property indicates if start position can be found unambiguously, but codec can make some assumptions
        and return some value from findCharacterStart basing on this assumption. For example, utf-16 codec cannot
        determine if byte represents high or low byte in 2-byte character, but can determine if pair of bytes
        at some position is high or low surrogate.
        """
        raise NotImplementedError()

    @property
    def unitSize(self):
        """Unit size is greatest common divisor of all possible character sizes.
        """
        raise NotImplementedError()

    def findCharacterStart(self, document, position):
        """Finds start of character that has byte at :position:.
        """
        return self.getCharacterData(document, position).startPosition

    def getCharacterSize(self, document, position):
        """Finds number of bytes occupied by char that has byte at position. Can return -1 if number of bytes cannot be
        determined.
        """
        return self.getCharacterData(document, position).bytesCount

    def decodeCharacter(self, document, position):
        """Converts character that has byte at :position: to Python string.
        """
        return self.getCharacterData(document, position).unicode

    def encodeString(self, text):
        """Converts string to sequence of bytes in this encoding.
        """
        raise NotImplementedError()

    def canEncode(self, text):
        """Returns True if text can be converted to this encoding, False otherwise
        """
        raise NotImplementedError()

    def getCharacterData(self, document, position):
        """Returns CharacterData object that describes properties of character that
        includes byte at :position: in :document:
        Attributes of this object has the following meaning:
            .unicode - Python string, decoded from character;
            .document - document from which data are read, as passed to this method;
            .startPosition - position which was assumed as position of first byte of
                             decoded character;
            .bytesCount - number of bytes that was used;
            .documentData - bytes decoded character consist of in this encoding
        """
        raise NotImplementedError()


class QtProxyCodec(AbstractCodec):
    """Codec that encapsulates QTextCodec class"""
    def __init__(self, qcodec):
        AbstractCodec.__init__(self, qcodec.name())
        self._qcodec = qcodec

    def canEncode(self, text):
        return self._qcodec.canEncode(text)


class SingleByteEncodingCodec(QtProxyCodec):
    def __init__(self, codec):
        QtProxyCodec.__init__(self, codec)

    @property
    def fixedSize(self):
        return 1

    @property
    def canDetermineCharacterStart(self):
        return True

    @property
    def unitSize(self):
        return 1

    def encodeString(self, text):
        return self._qcodec.fromUnicode(text)

    def getCharacterData(self, document, position):
        d = CharacterData()
        data = document.read(position, 1)
        if len(data) != 1:
            raise PartialCharacterError()

        d.unicode = self._qcodec.toUnicode(data)
        d.startPosition = position
        d.document = document
        d.bytesCount = 1
        d.documentData = data

        if len(d.unicode) != 1:
            raise EncodingError()

        return d


class Utf16Codec(QtProxyCodec):
    def __init__(self, little_endian=True):
        QtProxyCodec.__init__(self, QTextCodec.codecForName('utf-16le' if little_endian else 'utf-16be'))
        self.littleEndian = little_endian

    @property
    def fixedSize(self):
        return -1 # we support surrogates, so utf16 is not fixed width for us

    @property
    def canDetermineCharacterStart(self):
        return False # we can determine if word is high or low surrogate, but cannot determine if character starts on
                     # position or position + 1

    @property
    def unitSize(self):
        return 2

    def encodeString(self, text):
        # looks like QTextCodec adds BOM before converted string. It is not what we want.
        converted = self._qcodec.fromUnicode(text)
        if len(converted) >= 2 and converted[:2] in (b'\xff\xfe', b'\xfe\xff'):
            return converted[2:]
        else:
            return converted

    def getCharacterData(self, document, position):
        import hex.valuecodecs as valuecodecs

        d = CharacterData()
        d.document = document

        word_codec = valuecodecs.IntegerCodec(valuecodecs.IntegerCodec.Format16Bit, False,
                                              valuecodecs.LittleEndian if self.littleEndian else valuecodecs.BigEndian)

        raw_data = document.read(position, 2)
        if len(raw_data) != 2:
            raise PartialCharacterError()
        word = word_codec.decode(raw_data)
        if 0xd800 <= word <= 0xdbff:
            # high surrogate, next word should be trail surrogate... check it
            trail_word_data = document.read(position + 2, 2)
            if len(trail_word_data) < 2:
                raise PartialCharacterError()
            trail_word = word_codec.decode(trail_word_data)
            if not (0xdc00 <= trail_word <= 0xdfff):
                raise EncodingError('lead surrogate without trail surrogate')
            d.startPosition = position
            d.unicode = self._qcodec.toUnicode(raw_data + trail_word_data)
            d.documentData = raw_data + trail_word_data
            d.bytesCount = 4
        elif 0xdc00 <= word <= 0xdfff:
            # low surrogate, previous word should be lead surrogate
            if position < 2:
                raise PartialCharacterError()
            lead_word_data = document.read(position - 2, 2)
            lead_word = word_codec.decode(lead_word_data)
            if not (0xd800 <= lead_word <= 0xdbff):
                raise PartialCharacterError('trail surrogate without lead surrogate')
            d.startPosition = position - 2
            d.unicode = self._qcodec.toUnicode(lead_word_data + raw_data)
            d.documentData = lead_word_data + raw_data
            d.bytesCount = 4
        else:
            d.startPosition = position
            d.unicode = self._qcodec.toUnicode(raw_data)
            d.bytesCount = 2

        if len(d.unicode) != 1:
            raise EncodingError()

        return d


class Utf32Codec(QtProxyCodec):
    def __init__(self, little_endian=True):
        QtProxyCodec.__init__(self, QTextCodec.codecForName('utf-32le' if little_endian else 'utf-32be'))
        self.littleEndian = little_endian

    @property
    def fixedSize(self):
        return 4

    @property
    def canDetermineCharacterStart(self):
        return False

    @property
    def unitSize(self):
        return 4

    def getCharacterData(self, document, position):
        d = CharacterData()
        data = document.read(position, 4)
        if len(data) != 4:
            raise PartialCharacterError()
        d.document = document
        d.startPosition = position
        d.documentData = data
        d.unicode = self._qcodec.toUnicode(data)
        if len(d.unicode) != 1:
            raise EncodingError()
        d.bytesCount = 4
        return d

    def encodeString(self, text):
        converted = bytes(self._qcodec.fromUnicode(text))
        if len(converted) >= 8 and converted[:4] in (b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff'):
            return converted[4:]
        else:
            return converted


class Utf8Codec(QtProxyCodec):
    def __init__(self):
        QtProxyCodec.__init__(self, QTextCodec.codecForName('utf-8'))

    @property
    def fixedSize(self):
        return -1

    @property
    def canDetermineCharacterStart(self):
        return True

    @property
    def unitSize(self):
        return 1

    def getCharacterData(self, document, position):
        d = CharacterData()
        d.document = document

        back_position = max(0, position - 5)
        data = bytes(document.read(back_position, position - back_position + 1))
        if not data:
            raise PartialCharacterError()

        if not (data[-1] & 0x80):
            # if highest bit is off, this is first character
            d.startPosition = position
            first_byte_index = len(data) - 1
        else:
            for first_byte_index in reversed(range(len(data))):
                if (data[first_byte_index] & 0xc0) == 0xc0:
                    # this byte can be first octet
                    d.startPosition = first_byte_index + back_position
                    break
            else:
                raise EncodingError('invalid utf-8 sequence: failed to find first octet')

        # now find length of sequence
        first_byte = data[first_byte_index]
        if (first_byte & 0xfc) == 0xfc:
            d.bytesCount = 6
        elif (first_byte & 0xf8) == 0xf8:
            d.bytesCount = 5
        elif (first_byte & 0xf0) == 0xf0:
            d.bytesCount = 4
        elif (first_byte & 0xe0) == 0xe0:
            d.bytesCount = 3
        elif (first_byte & 0xc0) == 0xc0:
            d.bytesCount = 2
        else:
            d.bytesCount = 1

        if first_byte_index + d.bytesCount > len(data):
            d.documentData = document.read(d.startPosition, d.bytesCount)
        else:
            d.documentData = data[first_byte_index:first_byte_index+d.bytesCount]

        # and decode character
        d.unicode = self._qcodec.toUnicode(d.documentData)
        if len(d.unicode) != 1:
            raise EncodingError('failed to decode utf-8 sequence')

        return d

    def encodeString(self, text):
        encoded = self._qcodec.fromUnicode(text)
        if len(encoded) > 3 and encoded.startswith('\xef\xbb\xbf'):
            return encoded[3:]
        else:
            return encoded


singlebyte_encodings = (
    'ISO 8859-1',
    'ISO 8859-2',
    'ISO 8859-3',
    'ISO 8859-4',
    'ISO 8859-5',
    'ISO 8859-6',
    'ISO 8859-7',
    'ISO 8859-8',
    'ISO 8859-9',
    'ISO 8859-10',
    'ISO 8859-13',
    'ISO 8859-14',
    'ISO 8859-15',
    'ISO 8859-16',
    'Windows-1250',
    'Windows-1251',
    'Windows-1252',
    'Windows-1253',
    'Windows-1254',
    'Windows-1255',
    'Windows-1256',
    'Windows-1257',
    'Windows-1258',
    'IBM-850',
    'IBM-866',
    'IBM-874',
    'AppleRoman',
    'KOI8-R',
    'KOI8-U',
    'roman8'
)

encodings = {
    'UTF-8': Utf8Codec(),
    'UTF-16LE': Utf16Codec(little_endian=True),
    'UTF-16BE': Utf16Codec(little_endian=False),
    'UTF-32LE': Utf32Codec(little_endian=True),
    'UTF-32BE': Utf32Codec(little_endian=False)
}

for encoding in singlebyte_encodings:
    qcodec = QTextCodec.codecForName(encoding)
    if qcodec is not None:
        encodings[encoding] = SingleByteEncodingCodec(qcodec)


def getCodec(name):
    name = name.lower()
    for key in encodings.keys():
        if key.lower() == name:
            return encodings[key]
    return None
