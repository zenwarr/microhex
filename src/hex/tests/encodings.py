import unittest
import hex.encodings as encodings
import hex.utils as utils

class TestEncodings(unittest.TestCase):
    def do_test_codec(self, codec, encoded, unicode):
        cursor = utils.DataCursor(encoded)
        current_start = 0
        for char_index in range(len(unicode)):
            ch = codec.getCharacterData(cursor)
            self.assertEqual(ch.unicode, unicode[char_index])
            if ch.bufferRange.startPosition != current_start:
                pass
            self.assertEqual(ch.bufferRange.startPosition, current_start)
            current_start += ch.bufferRange.size
            self.assertTrue(current_start <= len(encoded))
            cursor.advance(ch.bufferRange.size)

    def test_singlebyte(self):
        self.do_test_codec(encodings.getCodec('Windows-1251'), b'Hello! \xcf\xf0\xe8\xe2\xe5\xf2!', 'Hello! Привет!')

    def test_utf16(self):
        codec = encodings.getCodec('utf-16le')

        self.do_test_codec(codec, b'H\x00e\x00l\x00l\x00o\x00!\x00\x20\x00'
                           b'\x1f\x04\x40\x04\x38\x04\x32\x04\x35\x04\x42\x04\x21\x00', 'Hello! Привет!')

        # and with surrogates too...
        self.do_test_codec(codec, b'\x69\xd8\xd6\xde', '\U0002a6d6')

        # broken surrogate - only lead part
        cursor = utils.DataCursor(b'\x69\xd8')
        self.assertRaises(encodings.PartialCharacterError, lambda: codec.getCharacterData(cursor))

        # broken surrogate - only trail part
        cursor = utils.DataCursor(b'\xd6\xde')
        self.assertRaises(encodings.PartialCharacterError, lambda: codec.getCharacterData(cursor))

        # cursor not in start of character
        cursor = utils.DataCursor(b'\x69\xd8\xd6\xde')
        cursor.advance(2)
        self.assertEqual(codec.getCharacterData(cursor).unicode, '\U0002a6d6')

        # encode
        self.assertEqual(codec.encodeString('Hello'), b'H\x00e\x00l\x00l\x00o\x00')

        self.assertEqual(codec.encodeString('\U0002a6d6'), b'\x69\xd8\xd6\xde')

    def test_utf32(self):
        codec = encodings.getCodec('utf-32le')

        # decode...
        self.do_test_codec(codec, b'h\x00\x00\x00i\x00\x00\x00!\x00\x00\x00', 'hi!')

        # and encode. Simple codec - simple test.
        self.assertEqual(codec.encodeString('hi!'), b'h\x00\x00\x00i\x00\x00\x00!\x00\x00\x00')

    def test_utf8(self):
        codec = encodings.getCodec('utf-8')

        # ascii-like
        self.do_test_codec(codec, b'hi!', 'hi!')

        # two-byte character
        cursor = utils.DataCursor(b'\xc2\xa2')
        self.assertEqual(codec.getCharacterData(cursor).unicode, '\u00a2')

        # three-byte character
        cursor = utils.DataCursor(b'\xe2\x82\xac')
        self.assertEqual(codec.getCharacterData(cursor).unicode, '\u20ac')

        # four-byte character
        cursor = utils.DataCursor(b'\xf0\xa4\xad\xa2')
        self.assertEqual(codec.getCharacterData(cursor).unicode, '\U00024b62')

        # cursor in the middle of character
        cursor.advance(2)
        self.assertEqual(codec.getCharacterData(cursor).unicode, '\U00024b62')

        cursor.advance(1)
        self.assertEqual(codec.getCharacterData(cursor).unicode, '\U00024b62')

        # overlong encoded characters are not allowed
        cursor = utils.DataCursor(b'\xf0\x82\x82\xac')
        self.assertRaises(encodings.EncodingError, lambda: codec.getCharacterData(cursor))

    def test_utf8_unexpected_continuation(self):
        cursor = utils.DataCursor(b'\xc0')
        self.assertRaises(encodings.EncodingError, lambda: encodings.getCodec('utf-8').getCharacterData(cursor))

    def test_utf8_partial_character(self):
        cursor = utils.DataCursor(b'\xf0\x00\x00\x00\x00')
        self.assertRaises(encodings.PartialCharacterError, lambda: encodings.getCodec('utf-8').getCharacterData(cursor))

    def test_utf8_partial_character_short_buffer(self):
        cursor = utils.DataCursor(b'\xf0')
        self.assertRaises(encodings.PartialCharacterError, lambda: encodings.getCodec('utf-8').getCharacterData(cursor))

    def test_utf8_find_start(self):
        cursor = utils.DataCursor(b'\xd0\xbf', 1)
        chd = encodings.getCodec('utf-8').getCharacterData(cursor)
        self.assertEqual(chd.unicode, 'п')
        self.assertEqual(chd.bufferRange.startPosition, 0)
        self.assertEqual(chd.bufferRange.size, 2)

