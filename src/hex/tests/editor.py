import unittest
from hex.editor import Editor, Span, DataSpan, FillSpan, OutOfBoundsError


class TestEditor(unittest.TestCase):
    def test(self):
        editor = Editor()

        self.assertEqual(len(editor), 0)
        self.assertEqual(len(editor.spans), 0)
        self.assertFalse(editor.isModified)

        data_span = DataSpan(editor, b'Hello, World!')
        editor.appendSpan(data_span)
        self.assertTrue(editor.isModified)
        self.assertEqual(len(editor), len('Hello, World!'))
        self.assertEqual(len(editor.spans), 1)
        self.assertEqual(editor.spanAtPosition(0), data_span)
        self.assertFalse(editor.spanAtPosition(29))
        self.assertEqual(len(editor.spansInRange(0, 5)[0]), 1)
        self.assertRaises(OutOfBoundsError, lambda: editor.spansInRange(0, 200))

        self.assertEqual(editor.read(1, 4), b'ello')

        editor.insertSpan(1, DataSpan(editor, b'!!!'))
        self.assertEqual(editor.readAll(), b'H!!!ello, World!')
        self.assertEqual(len(editor.spans), 3)
        self.assertEqual(len(editor), len(data_span) + 3)
        self.assertEqual(len(editor.spanAtPosition(0)), 1)
        self.assertEqual(len(editor.spanAtPosition(1)), 3)
        self.assertEqual(len(editor.spanAtPosition(6)), 12)

        self.assertRaises(OutOfBoundsError, lambda: editor.insertSpan(30, DataSpan(editor, b'!!!')))
        self.assertRaises(OutOfBoundsError, lambda: editor.insertSpan(-1, DataSpan(editor, b'!!!')))

        self.assertEqual(editor.readAll(), b'H!!!ello, World!')
        self.assertEqual(len(editor.spans), 3)
        self.assertEqual(len(editor), len(data_span) + 3)
        self.assertEqual(len(editor.spanAtPosition(0)), 1)
        self.assertEqual(len(editor.spanAtPosition(1)), 3)
        self.assertEqual(len(editor.spanAtPosition(6)), 12)

        editor.remove(1, 3)
        self.assertEqual(len(editor.spans), 2)
        self.assertEqual(editor.readAll(), b'Hello, World!')

        editor.writeSpan(5, FillSpan(editor, b'?', 2))
        self.assertEqual(editor.readAll(), b'Hello??World!')

        editor.writeSpan(20, DataSpan(editor, b'Yeah!'))
        self.assertEqual(editor.readAll(), b'Hello??World!\0\0\0\0\0\0\0Yeah!')

        editor.clear()
        self.assertEqual(len(editor), 0)
        self.assertEqual(len(editor.spans), 0)

        editor.writeSpan(0, data_span)
        self.assertEqual(len(editor.takeSpans(2, 3)[0]), 1)
        self.assertEqual(len(editor.spans), 3)
        self.assertEqual(len(editor.spans[0]), 2)
        self.assertEqual(len(editor.spans[1]), 3)
        self.assertEqual(len(editor.spans[2]), 8)

        self.assertEqual(editor.readAtEnd(5, 20), b', World!')

        self.assertTrue(editor.isModified)
