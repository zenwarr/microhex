import unittest
from hex.editor import Editor, Span, DataSpan, FillSpan, OutOfBoundsError
from hex.devices import BufferDevice
from PyQt4.QtCore import QBuffer, QByteArray


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
        self.assertEqual(len(editor.takeSpans(2, 3)), 1)
        self.assertEqual(len(editor.spans), 3)
        self.assertEqual(len(editor.spans[0]), 2)
        self.assertEqual(len(editor.spans[1]), 3)
        self.assertEqual(len(editor.spans[2]), 8)

        self.assertEqual(editor.readAtEnd(5, 20), b', World!')

        self.assertTrue(editor.isModified)

        self.undoTest()

    def undoTest(self):
        editor = Editor(BufferDevice(QByteArray(b'Hello, World!'), read_only=True))

        editor.insertSpan(3, DataSpan(editor, b'000'))
        self.assertEqual(editor.readAll(), b'Hel000lo, World!')
        self.assertTrue(editor.isModified)

        self.assertTrue(editor.canUndo())
        self.assertFalse(editor.canRedo())

        editor.undo()
        self.assertEqual(editor.readAll(), b'Hello, World!')
        self.assertFalse(editor.isModified)

        editor.redo()
        self.assertEqual(editor.readAll(), b'Hel000lo, World!')

        # and again...
        editor.undo()
        self.assertEqual(editor.readAll(), b'Hello, World!')
        self.assertFalse(editor.isModified)

        self.assertFalse(editor.canUndo())
        self.assertTrue(editor.canRedo())

        # how we will create another action. New redo branch should be created
        editor.appendSpan(DataSpan(editor, b' Yeah!'))
        self.assertEqual(editor.readAll(), b'Hello, World! Yeah!')

        self.assertTrue(editor.canUndo())
        self.assertFalse(editor.canRedo())

        editor.undo()

        self.assertEqual(editor.readAll(), b'Hello, World!')

        # at this point we should have two redo branches
        branches = editor.alternativeBranches()
        self.assertEqual(len(branches), 1)

        # try to switch to another branch
        editor.redo(branches[0])
        self.assertEqual(editor.readAll(), b'Hel000lo, World!')

        editor.undo()
        self.assertEqual(editor.readAll(), b'Hello, World!')

        # still be should have two branches at this point
        self.assertEqual(len(editor.alternativeBranches()), 1)

        editor.remove(0, 7)
        self.assertEqual(editor.readAll(), b'World!')

        editor.undo()
        self.assertEqual(editor.readAll(), b'Hello, World!')
