import codecs
import hex.utils as utils


class EncodingError(ValueError):
    pass


class PartialCharacterError(EncodingError):
    def __init__(self, desc=''):
        EncodingError.__init__(self, utils.tr('only part of character is available - {0}').format(desc))


class CharacterData(object):
    def __init__(self, unicode, data_range, buffer_cached_data=None):
        self.unicode = unicode
        self._bufferRange = data_range
        self._bufferCachedData = buffer_cached_data

    @property
    def bufferRange(self):
        return self._bufferRange or utils.DataRange(b'', 0, 0)

    @property
    def bufferData(self):
        if self._bufferCachedData is not None:
            return self._bufferCachedData
        else:
            return self.bufferRange.createCursor()[0:self.bufferRange.size]


class AbstractCodec(object):
    def __init__(self, name):
        self.name = name

    @property
    def fixedSize(self):
        """Returns number of bytes used to encode one character if encoding is fixed-width. Should return -1 for
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

    def findCharacterStart(self, cursor):
        """Finds start of character that has byte cursor points to.
        """
        return self.getCharacterData(cursor).bufferRange.startPosition

    def getCharacterSize(self, cursor):
        """Finds number of bytes occupied by char that has byte at position. Can return -1 if number of bytes cannot be
        determined.
        """
        return self.getCharacterData(cursor).bufferRange.size

    def toUnicode(self, cursor):
        return self.getCharacterData(cursor).unicode

    def encodeString(self, text):
        """Converts string to sequence of bytes in this encoding.
        """
        raise NotImplementedError()

    def canEncode(self, text):
        """Returns True if text can be converted to this encoding, False otherwise
        """
        raise NotImplementedError()

    def getCharacterData(self, cursor):
        """Returns CharacterData object that describes properties of character that contains byte cursor points to.
        """
        raise NotImplementedError()


class ProxyCodec(AbstractCodec):
    def __init__(self, encoding_name):
        AbstractCodec.__init__(self, encoding_name)
        self._codecInfo = codecs.lookup(encoding_name)

    def canEncode(self, text):
        try:
            self._codecInfo.encode(text)[0]
            return True
        except ValueError:
            return False


class SingleByteEncodingCodec(ProxyCodec):
    def __init__(self, encoding):
        ProxyCodec.__init__(self, encoding)

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
        try:
            return self._codecInfo.encode(text)[0]
        except ValueError:
            raise EncodingError()

    def getCharacterData(self, cursor):
        try:
            data = cursor[0:1]
        except IndexError:
            raise PartialCharacterError()

        try:
            unicode = self._codecInfo.decode(data)[0]
        except ValueError as err:
            raise EncodingError(str(err))

        if len(unicode) != 1:
            print(unicode)
            raise EncodingError()

        return CharacterData(unicode, cursor.bufferRange(0, 1), data)


class Utf16Codec(ProxyCodec):
    def __init__(self, little_endian=True):
        ProxyCodec.__init__(self, 'utf-16le' if little_endian else 'utf-16be')
        self.littleEndian = little_endian

    @property
    def fixedSize(self):
        return -1  # we support surrogates, so utf16 is not fixed width for us

    @property
    def canDetermineCharacterStart(self):
        return False  # we can determine if word is high or low surrogate, but cannot determine if character starts on
                      # position or position + 1

    @property
    def unitSize(self):
        return 2

    def encodeString(self, text):
        try:
            return self._codecInfo.encode(text)[0]
        except ValueError:
            raise EncodingError()

    def getCharacterData(self, cursor):
        import hex.valuecodecs as valuecodecs

        word_codec = valuecodecs.IntegerCodec(valuecodecs.IntegerCodec.Format16Bit, False,
                                              valuecodecs.LittleEndian if self.littleEndian else valuecodecs.BigEndian)

        try:
            raw_data = cursor[0:2]
        except IndexError:
            raise PartialCharacterError()

        word = word_codec.decode(raw_data)
        if 0xd800 <= word <= 0xdbff:
            # lead surrogate, next word should be trail surrogate... check it
            no_surrogate_error = 'lead surrogate without trail surrogate'

            try:
                trail_word_data = cursor[2:4]
            except IndexError:
                raise PartialCharacterError(no_surrogate_error)

            trail_word = word_codec.decode(trail_word_data)
            if not (0xdc00 <= trail_word <= 0xdfff):
                raise PartialCharacterError(no_surrogate_error)

            raw_data += trail_word_data
            rng = cursor.bufferRange(0, 4)
        elif 0xdc00 <= word <= 0xdfff:
            # trail surrogate, previous word should be lead surrogate
            no_surrogate_error = 'trail surrogate without lead surrogate'

            try:
                lead_word_data = cursor[-2:0]
            except IndexError:
                raise PartialCharacterError(no_surrogate_error)

            lead_word = word_codec.decode(lead_word_data)
            if not (0xd800 <= lead_word <= 0xdbff):
                raise PartialCharacterError(no_surrogate_error)

            raw_data = lead_word_data + raw_data
            rng = cursor.bufferRange(-2, 2)
        else:
            rng = cursor.bufferRange(0, 2)

        try:
            unicode = self._codecInfo.decode(raw_data)[0]
        except ValueError:
            raise EncodingError()

        if len(unicode) != 1:
            raise EncodingError()

        return CharacterData(unicode, rng, raw_data)


class Utf32Codec(ProxyCodec):
    def __init__(self, little_endian=True):
        ProxyCodec.__init__(self, 'utf-32le' if little_endian else 'utf-32be')
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

    def getCharacterData(self, cursor):
        try:
            data = cursor[0:4]
        except IndexError:
            raise PartialCharacterError()

        try:
            unicode = self._codecInfo.decode(data)[0]
        except ValueError:
            raise EncodingError()

        if len(unicode) != 1:
            raise EncodingError()
        return CharacterData(unicode, cursor.bufferRange(0, 4), data)

    def encodeString(self, text):
        try:
            return self._codecInfo.encode(text)[0]
        except ValueError:
            raise EncodingError()


class Utf8Codec(ProxyCodec):
    def __init__(self):
        ProxyCodec.__init__(self, 'utf-8')

    @property
    def fixedSize(self):
        return -1

    @property
    def canDetermineCharacterStart(self):
        return True

    @property
    def unitSize(self):
        return 1

    def getCharacterData(self, cursor):
        cursor = cursor.clone()

        # find first character byte. Advance cursor to this byte.
        try:
            first_byte = cursor[0]
        except IndexError:
            raise PartialCharacterError()
        if (first_byte >> 6) == 0b10:
            # if this is continuation byte (10xxxxxx), look backwards to find first byte in sequence
            error_text = 'invalid utf-8 sequence: continuation byte without leading byte'
            for x in range(5):
                cursor.advance(-1)

                try:
                    first_byte = cursor[0]
                except IndexError:
                    raise PartialCharacterError(error_text)

                if (first_byte & 0b11000000) == 0b11000000:
                    # found first character of multi byte sequence
                    break
                elif (first_byte & 0b10000000) == 0:
                    # single byte character - invalid sequence
                    raise EncodingError(error_text)
            else:
                raise EncodingError(error_text)

        # now find length of sequence
        if (first_byte & 0b10000000) == 0:
            char_length = 1
        elif (first_byte & 0b11111100) == 0b11111100:
            char_length = 6
        elif (first_byte & 0b11111000) == 0b11111000:
            char_length = 5
        elif (first_byte & 0b11110000) == 0b11110000:
            char_length = 4
        elif (first_byte & 0b11100000) == 0b11100000:
            char_length = 3
        elif (first_byte & 0b11000000) == 0b11000000:
            char_length = 2
        else:
            raise EncodingError('invalid utf-8 sequence: leading byte has incorrect value')

        # check if all there are char_length - 1 continuation bytes following
        try:
            char_data = cursor[0:char_length]
        except IndexError:
            raise PartialCharacterError()
        if not all(byte >> 6 == 0b10 for byte in char_data[1:]):
            raise PartialCharacterError()

        # and decode character
        try:
            unicode = self._codecInfo.decode(char_data)[0]
        except ValueError:
            raise EncodingError('failed to decode utf-8 sequence')

        return CharacterData(unicode, cursor.bufferRange(0, char_length), char_data)

    def encodeString(self, text):
        try:
            return self._codecInfo.encode(text)[0]
        except ValueError:
            raise EncodingError()


singlebyte_encodings = (
    'ASCII',
    'ISO-8859-1',
    'ISO-8859-2',
    'ISO-8859-3',
    'ISO-8859-4',
    'ISO-8859-5',
    'ISO-8859-6',
    'ISO-8859-7',
    'ISO-8859-8',
    'ISO-8859-9',
    'ISO-8859-10',
    'ISO-8859-13',
    'ISO-8859-14',
    'ISO-8859-15',
    'ISO-8859-16',
    'Windows-1250',
    'Windows-1251',
    'Windows-1252',
    'Windows-1253',
    'Windows-1254',
    'Windows-1255',
    'Windows-1256',
    'Windows-1257',
    'Windows-1258',
    # 'IBM-850',
    # 'IBM-866',
    # 'IBM-874',
    # 'AppleRoman',
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
    try:
        codec_info = codecs.lookup(encoding)
    except LookupError:
        print('failed to install codec for ' + encoding)
        continue

    encodings[encoding] = SingleByteEncodingCodec(encoding)


def getCodec(name):
    name = name.lower()
    for key in encodings.keys():
        if key.lower() == name:
            return encodings[key]
    return None


from PyQt4.QtCore import pyqtSignal, Qt
from PyQt4.QtGui import QComboBox


class EncodingsCombo(QComboBox):
    encodingNameChanged = pyqtSignal(str)
    encodingChanged = pyqtSignal(AbstractCodec)

    def __init__(self, parent, initial_encoding=None):
        QComboBox.__init__(self, parent)
        if isinstance(initial_encoding, AbstractCodec):
            initial_encoding = initial_encoding.name
        # fill combo box with available encodings
        for enc_name in encodings.keys():
            self.addItem(enc_name, encodings[enc_name])
            if initial_encoding is not None and enc_name.lower() == initial_encoding.lower():
                self.setCurrentIndex(self.count() - 1)
        self.currentIndexChanged[str].connect(self._onCurrentIndexChanged)

    @property
    def encodingName(self):
        return self.currentText()

    @property
    def encoding(self):
        return getCodec(self.currentText())

    @encoding.setter
    def encoding(self, new_enc):
        if isinstance(new_enc, AbstractCodec):
            new_enc = new_enc.name
        index = self.findText(new_enc, Qt.MatchFixedString)
        if index >= 0:
            self.setCurrentIndex(index)

    @encodingName.setter
    def encodingName(self, new_enc):
        self.encoding = new_enc

    def _onCurrentIndexChanged(self, new_text):
        self.encodingNameChanged.emit(new_text)
        self.encodingChanged.emit(encodings.get(new_text))
