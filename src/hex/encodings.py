from PyQt4.QtCore import QTextCodec
import hex.utils as utils


class EncodingError(ValueError):
    pass


class PartialCharacterError(EncodingError):
    def __init__(self, desc=''):
        EncodingError.__init__(self, utils.tr('only part of character is available - {0}').format(desc))


class AbstractCodec(object):
    def __init__(self, name):
        self.name = name

    @property
    def fixedSize(self):
        """Returns number of bytes occupied by one character if encoding is fixed-byte. Should return -1 for multibyte
        encodings.
        """
        raise NotImplementedError()

    @property
    def canDetermineCharacterStart(self):
        """Returns True if codec can determine where character starts by any byte of this character. For example,
        for utf-8 encoding this property should return True, and False for utf-16 or utf-32 encodings. Note that
        this property indicates if start position can be found unambiguously, but codec can make some assumpitons
        and return some value from findCharacterStart basing on this assumption. For example, utf-16 codec cannot
        determine if some byte represents high or low byte in 2-byte character, but can determine if character
        that starts at some position is high or low surrogate.
        """
        raise NotImplementedError()

    @property
    def unitSize(self):
        """Unit size is maximal number of bytes any character size is multiplied by
        """
        raise NotImplementedError()

    def findCharacterStart(self, editor, position):
        """Finds start of character that has byte at :position:. Should raise EncodingError if self.canDetermineCharacterStart
        is False"""
        raise NotImplementedError()

    def getCharacterSize(self, editor, position):
        """Finds number of bytes occupied by char that has byte at position. Can return -1 if number of bytes cannot be
        determined.
        """
        raise NotImplementedError()

    def decodeCharacter(self, editor, position):
        """Converts character that has byte at :position: to Python string.
        """
        raise NotImplementedError()

    def encodeString(self, text):
        """Converts string to sequence of bytes in given encoding.
        """
        raise NotImplementedError()


class QtProxyCodec(AbstractCodec):
    def __init__(self, qcodec):
        AbstractCodec.__init__(self, qcodec.name())
        self._qcodec = qcodec


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

    def findCharacterStart(self, editor, position):
        return position

    def getCharacterSize(self, editor, position):
        return 1

    def decodeCharacter(self, editor, position):
        data = editor.readAtEnd(position, 1)
        return self._qcodec.toUnicode(data)

    def encodeString(self, text):
        return self._qcodec.fromUnicode(text)


class Utf16Codec(QtProxyCodec):
    def __init__(self, little_endian=True):
        QtProxyCodec.__init__(self, QTextCodec.codecForName('utf-16le' if little_endian else 'utf-16be'))
        self.littleEndian = little_endian

    @property
    def fixedSize(self):
        return -1 # we will support surrogates, so utf16 is not fixedbyte for us

    @property
    def canDetermineCharacterStart(self):
        return False # we can determine if word is high or low surrogate, but cannot determine if character start on
                  # position or position + 1

    @property
    def unitSize(self):
        return 2

    def findCharacterStart(self, editor, position):
        import hex.valuecodecs as valuecodecs

        word = editor.readAtEnd(position, 2)
        if len(word) != 2:
            raise PartialCharacterError()

        vcodec = valuecodecs.IntegerCodec(valuecodecs.IntegerCodec.Format16Bit, False,
                                        valuecodecs.LittleEndian if self.littleEndian else valuecodecs.BigEndian)
        word = vcodec.decode(word)

        if (word & 0xfc00) == 0xdc00:
            # low surrogate - this is second part of surrogate character
            # character itself starts at previous part...
            if position < 2:
                raise PartialCharacterError('low surrogate at start')
            position -= 2

        return position

    def getCharacterSize(self, editor, position):
        start = self.findCharacterStart(editor, position)
        if start < position:
            # that was low surrogate at :position:, so length of our char is 4 bytes
            return 4
        else:
            return 2

    def decodeCharacter(self, editor, position):
        data = editor.readAtEnd(self.findCharacterStart(editor, position), self.getCharacterSize(editor, position))
        decoded = self._qcodec.toUnicode(data)
        return decoded

    def encodeString(self, text):
        return self._qcodec.fromUnicode(text)


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

    def findCharacterStart(self, editor, position):
        raise EncodingError()

    def getCharacterSize(self, editor, position):
        return 4

    def decodeCharacter(self, editor, position):
        data = editor.readAtEnd(position, 4)
        if len(data) != 4:
            raise PartialCharacterError()
        return self._qcodec.toUnicode(data)

    def encodeString(self, text):
        return self._qcodec.fromUnicode(text)


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

    def findCharacterStart(self, editor, position):
        back_position = max(0, position - 5)
        data = editor.read(back_position, position - back_position + 1)
        if not (data[-1] & 0x80):
            # if highest bit is off, this is first character
            return position

        for byte_index in reversed(range(len(data))):
            if (data[byte_index] & 0xc0) == 0xc0:
                # this can be first byte
                return byte_index + back_position
        else:
            raise EncodingError()

    def getCharacterSize(self, editor, position):
        start = self.findCharacterStart(editor, position)
        first_byte = editor.read(start, 1)[0]
        if (first_byte & 0xfc) == 0xfc:
            return 6
        elif (first_byte & 0xf8) == 0xf8:
            return 5
        elif (first_byte & 0xf0) == 0xf0:
            return 4
        elif (first_byte & 0xe0) == 0xe0:
            return 3
        elif (first_byte & 0xc0) == 0xc0:
            return 2
        else:
            return 1

    def decodeCharacter(self, editor, position):
        data = editor.read(self.findCharacterStart(editor, position), self.getCharacterSize(editor, position))
        decoded = self._qcodec.toUnicode(data)
        if len(decoded) != 1:
            raise EncodingError('failed to decode utf-8 sequence')
        return decoded

    def encodeString(self, text):
        return self._qcodec.fromUnicode(text)


singlebyte_encodings = {
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
    'IBM-850'
    'IBM-866',
    'IBM-874'
    'AppleRoman',
    'KOI8-R'
    'KOI8-U'
    'roman8'
}

encodings = {
    'UTF-8': Utf8Codec(),
    'UTF-16LE': Utf16Codec(little_endian=True),
    'UTF-16BE': Utf16Codec(little_endian=False),
    'UTF-32LE': Utf32Codec(little_endian=True),
    'UTF-32BE': Utf32Codec(little_endian=False)
}

for encoding in singlebyte_encodings:
    global encodings

    qcodec = QTextCodec.codecForName(encoding)
    if qcodec is not None:
        encodings[encoding] = SingleByteEncodingCodec(qcodec)


def getCodec(name):
    name = name.lower()
    for key in encodings.keys():
        if key.lower() == name:
            return encodings[key]
    return None
