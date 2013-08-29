from unittest import TestCase
from unittest.mock import Mock, call
from hex.utils import DataCursor, CursorInactiveError, DocumentCursor, MaximalPosition


class CursorMock(DataCursor):
    def __init__(self, data, override_buffer_length=-1):
        super().__init__(data, override_buffer_length=override_buffer_length)
        self._write, self._replace, self._insert, self._remove = Mock(), Mock(), Mock(), Mock()


class CursorTest(TestCase):
    def test_initial(self):
        cursor = DataCursor(b'Lorem ipsum')
        self.assertEqual(cursor.leftBoundary, 0)
        self.assertEqual(cursor.rightBoundary, len(b'Lorem ipsum'))
        self.assertEqual(cursor.offset, 0)
        self.assertEqual(cursor.position, 0)

    def test_advance(self):
        cursor = DataCursor(b'Lorem ipsum')
        test_data = (3, 0, -1, 4, -6, -1, 100)
        for d in test_data:
            d_pos = cursor.offset + d
            cursor.advance(d)
            self.assertEqual(cursor.offset, d_pos)

    def test_left_boundary(self):
        for d in ((2, -2), (100, -100), (-100, 100)):
            cursor = DataCursor(b'lorem')
            cursor.advance(d[0])
            self.assertEqual(cursor.leftBoundary, d[1])

    def test_right_boundary(self):
        for d in ((2, 3), (5, 0), (6, -1)):
            cursor = DataCursor(b'lorem')
            cursor.advance(d[0])
            self.assertEqual(cursor.rightBoundary, d[1])

    def test_is_valid_position(self):
        for d in ((0, True), (1, True), (5, False), (4, True), (6, False), (100, False), (-1, False)):
            cursor = DataCursor(b'lorem')
            cursor.advance(d[0])
            self.assertEqual(cursor.isAtValidPosition, d[1])

    def test_get_single_item(self):
        cursor = DataCursor(b'lorem')
        for c in b'lorem':
            self.assertEqual(cursor[0], c)
            cursor.advance(1)

        cursor = DataCursor(b'lorem')
        cursor.advance(-10)
        for c in b'lorem':
            self.assertEqual(cursor[10], c)
            cursor.advance(1)

    def test_get_single_item_out_of_range(self):
        for pos in (-1, -100, 5, 6, 100):
            cursor = DataCursor('lorem')
            cursor.advance(pos)
            self.assertRaises(IndexError, lambda: cursor[0])

    def test_get_slice(self):
        cursor = DataCursor(b'lorem')
        self.assertEqual(cursor[1:4], b'ore')

    def test_get_slice_auto(self):
        cursor = DataCursor(b'lorem')
        cursor.advance(3)
        self.assertEqual(cursor[:1], b'lore')
        self.assertEqual(cursor[-1:], b'rem')
        self.assertEqual(cursor[:], b'lorem')

    def test_replace_slice(self):
        cursor = CursorMock(b'lorem ipsum')
        cursor.advance(2)
        cursor[-1:3] = b'this is data'
        self.assertEqual(cursor._replace.call_count, 1)
        self.assertEqual(cursor._replace.call_args, call(1, 5, b'this is data'))

    def test_replace_single(self):
        cursor = CursorMock(b'lorem')
        cursor.advance(2)
        cursor[-2] = 0xfd
        self.assertEqual(cursor._replace.call_count, 1)
        self.assertEqual(cursor._replace.call_args, call(0, 1, b'\xfd'))

        cursor[-2] = b'\xfd'
        self.assertEqual(cursor._replace.call_args, call(0, 1, b'\xfd'))

    def test_write(self):
        cursor = CursorMock(b'lorem')
        cursor.advance(2)
        cursor.write(0, b'data')
        self.assertEqual(cursor._write.call_count, 1)
        self.assertEqual(cursor._write.call_args, call(2, b'data'))

    def test_insert(self):
        cursor = CursorMock(b'lorem')
        cursor.advance(2)
        cursor.insert(1, b'data')
        self.assertEqual(cursor._insert.call_args, call(3, b'data'))

    def test_remove_slice(self):
        cursor = CursorMock(b'lorem')
        cursor.advance(2)
        cursor.remove(-1, 2)
        self.assertEqual(cursor._remove.call_args, call(1, 4))

    def test_remove_single(self):
        cursor = CursorMock(b'lorem')
        cursor.advance(2)
        del cursor[0]
        self.assertEqual(cursor._remove.call_args, call(2, 3))

    def test_buffer_range(self):
        cursor = CursorMock(b'lorem')
        cursor.advance(2)
        rng = cursor.bufferRange(-2, -1)
        self.assertEqual(rng.startPosition, 0)
        self.assertEqual(rng.size, 1)

    def test_buffer_invalid(self):
        cursor = CursorMock(b'lorem')
        self.assertRaises(IndexError, lambda: cursor.bufferRange(-1, 2))
        self.assertRaises(IndexError, lambda: cursor.bufferRange(5, 1))

    def test_empty_buffer(self):
        cursor = CursorMock(b'')
        self.assertEqual(cursor.leftBoundary, 0)
        self.assertEqual(cursor.rightBoundary, 0)
        self.assertFalse(cursor.isAtValidPosition)
        self.assertRaises(IndexError, lambda: cursor[0])

    def test_limited(self):
        cursor = CursorMock(b'lorem', override_buffer_length=2)
        self.assertEqual(cursor.bufferLength, 2)
        self.assertRaises(IndexError, lambda: cursor.read(0, 3))
        cloned_cursor = cursor.clone()
        self.assertEqual(cloned_cursor.bufferLength, 2)

        limited = cursor.limited(10)
        self.assertEqual(limited.bufferLength, 2)


class DocumentMock:
    def __init__(self, data):
        self._data = data
        self.length = len(data)
        self.read = Mock(wraps=lambda pos, length: self._data[pos:pos+length])
        self.writeSpan, self.insertSpan, self.remove, self.beginComplexAction, self.endComplexAction = (Mock() for i in range(5))


class DocumentCursorTest(TestCase):
    def test_read(self):
        cursor = DocumentCursor(DocumentMock(b'lorem'))
        cursor.advance(2)
        self.assertEqual(cursor.read(0, 2), b're')
        self.assertEqual(cursor.read(-1, 3), b'orem')

    def test_read_invalid(self):
        cursor = DocumentCursor(DocumentMock(b'lorem'))
        self.assertRaises(IndexError, lambda: cursor[-1])
        self.assertRaises(IndexError, lambda: cursor[5])
        self.assertRaises(IndexError, lambda: cursor[3:6])

    def test_write(self):
        cursor = DocumentCursor(DocumentMock(b'lorem'))
        cursor.write(1, b'data')
        self.assertEqual(cursor._document.writeSpan.call_count, 1)
        call_args = cursor._document.writeSpan.call_args
        self.assertTrue(len(call_args) == 2)
        self.assertEqual(call_args[0][0], 1)
        self.assertTrue(call_args[0][1].read(0, call_args[0][1].length) == b'data')

        cursor.write(MaximalPosition, b'')

    def test_write_invalid(self):
        cursor = DocumentCursor(DocumentMock(b'lorem'))
        cursor.advance(2)
        self.assertRaises(IndexError, lambda: cursor.write(-3, b'd'))
        self.assertRaises(IndexError, lambda: cursor.write(MaximalPosition, b'd'))

    def test_replace(self):
        cursor = DocumentCursor(DocumentMock(b'lorem'))
        cursor[0:2] = b'data'
        self.assertEqual(cursor._document.insertSpan.call_count, 1)
        self.assertEqual(cursor._document.remove.call_count, 1)
        self.assertEqual(cursor._document.remove.call_args, call(0, 2))
        call_args = cursor._document.insertSpan.call_args[0]
        self.assertEqual(call_args[0], 0)
        self.assertEqual(call_args[1].read(0, call_args[1].length), b'data')

    def test_remove(self):
        cursor = DocumentCursor(DocumentMock(b'lorem'))
        del cursor[1:2]
        self.assertEqual(cursor._document.remove.call_args, call(1, 1))
