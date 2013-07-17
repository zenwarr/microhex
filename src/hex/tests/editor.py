import unittest
import threading
import time
from hex.editor import Editor, Span, DataSpan, FillSpan, OutOfBoundsError
from hex.devices import BufferDevice, deviceFromBytes
from PyQt4.QtCore import QByteArray
import hex.utils as utils


class TestEditor(unittest.TestCase):
    def test(self):
        editor = Editor(deviceFromBytes(b''))

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

        self.assertEqual(editor.read(5, 20), b', World!')

        self.assertTrue(editor.isModified)

    def test2(self):
        editor = Editor(deviceFromBytes(QByteArray(b'Hello')))

        editor.remove(0, 1)

        self.assertEqual(len(editor), 4)
        self.assertEqual(editor.readAll(), b'ello')
        self.assertTrue(editor.isModified)
        self.assertFalse(editor.isRangeModified(0, 4))

    def testUndo(self):
        editor = Editor(deviceFromBytes(QByteArray(b'Hello, World!')))

        editor.insertSpan(3, DataSpan(editor, b'000'))
        self.assertEqual(editor.readAll(), b'Hel000lo, World!')
        self.assertTrue(editor.isModified)
        self.assertFalse(editor.isRangeModified(0, 2))
        self.assertTrue(editor.isRangeModified(3, 1))
        self.assertFalse(editor.isRangeModified(10, 2))
        self.assertTrue(editor.isRangeModified(0, 5))

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

        # and again!
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

    def testSave(self):
        array = QByteArray(b'Hello, World!')

        editor = Editor(BufferDevice(array))

        editor.insertSpan(3, DataSpan(editor, b'000'))
        self.assertEqual(editor.readAll(), b'Hel000lo, World!')
        self.assertTrue(editor.isModified)

        editor.save()

        self.assertEqual(editor.readAll(), b'Hel000lo, World!')
        self.assertFalse(editor.isModified)

        self.assertFalse(editor.isRangeModified(0, 5))
        editor.insertSpan(10, DataSpan(editor, b'!!!'))
        self.assertFalse(editor.isRangeModified(0, 5))
        self.assertTrue(editor.isModified)

        self.assertEqual(array, b'Hel000lo, World!')

        editor.undo()
        self.assertEqual(editor.readAll(), b'Hel000lo, World!')
        self.assertFalse(editor.isModified)

        editor.undo()
        self.assertEqual(editor.readAll(), b'Hello, World!')
        self.assertTrue(editor.isModified)

        array2 = QByteArray()
        device2 = BufferDevice(array2)

        editor.save(device2)
        self.assertEqual(device2.read(0, len(device2)), b'Hello, World!')

    def testb1(self):
        editor = Editor(deviceFromBytes(QByteArray()))

        editor.insertSpan(40, DataSpan(editor, b'\x00'))
        editor.writeSpan(10, FillSpan(editor, b'\x00', 5))

        self.assertTrue(editor.isRangeModified(30, 1))

    def testb2(self):
        editor = Editor(deviceFromBytes(QByteArray(b'Hello, World!')))

        editor.writeSpan(5, DataSpan(editor, b'!!'))
        self.assertEqual(editor.readAll(), b'Hello!!World!')

        editor.undo()
        self.assertEqual(editor.readAll(), b'Hello, World!')
        self.assertFalse(editor.isModified)
        self.assertFalse(editor.isRangeModified(5, 1))

        editor.redo()
        self.assertEqual(editor.readAll(), b'Hello!!World!')
        self.assertTrue(editor.isModified)
        self.assertTrue(editor.isRangeModified(5, 1))

    def test3(self):
        editor = Editor(deviceFromBytes(QByteArray(b'Hello, World!')))

        cursor = editor.createReadCursor()
        with cursor.activate():
            self.assertEqual(cursor[0], b'H'[0])
            self.assertEqual(cursor[0:2], b'He')
            self.assertEqual(cursor.minimal, 0)
            self.assertEqual(cursor.maximal, -1)

            cursor.position = 5
            self.assertEqual(cursor[0], b','[0])
            self.assertEqual(cursor[0:3], b', W')
            self.assertEqual(cursor[-1:3], b'o, W')
            self.assertEqual(cursor.minimal, -5)
            self.assertEqual(cursor.maximal, -1)

            self.assertEqual(cursor[-20:100], b'Hello, World!')
            self.assertEqual(cursor[100:10], b'')
            self.assertEqual(cursor[100:110], b'')

        cursor = editor.createWriteCursor()
        with cursor.activate():
            cursor[0] = b'h'
            self.assertEqual(editor.readAll(), b'hello, World!')

            cursor[0:5] = b'World'
            self.assertEqual(editor.readAll(), b'World, World!')

            cursor[-4:3] = b'?'
            self.assertEqual(editor.readAll(), b'?ld, World!')

            for ch in b'?ld, World!':
                self.assertEqual(cursor.get()[0], ch)

            cursor.position = 0
            cursor[0:len(editor)] = b''
            self.assertEqual(editor.readAll(), b'')

            for ch in 'Hello, World!':
                cursor.put(bytes(ch, encoding='ascii'))

            self.assertEqual(editor.readAll(), b'Hello, World!')

    def test4(self):
        lock = utils.ReadWriteLock()

        lock.acquireRead()
        lock.acquireWrite()

        lock.releaseWrite()
        lock.releaseRead()

        lock.acquireWrite()
        lock.acquireRead()

        lock.releaseRead()
        lock.releaseWrite()

        lock.acquireRead()
        locked = False

        def another_thread():
            nonlocal locked

            lock.acquireRead()
            locked = True
            lock.releaseRead()

        threading.Thread(target=another_thread).start()
        time.sleep(1)
        self.assertTrue(locked)

        locked = False
        # still locked for read by main thread

        def another_thread2():
            nonlocal locked

            lock.acquireWrite()
            locked = True
            lock.releaseWrite()

        threading.Thread(target=another_thread2).start()
        time.sleep(1)
        self.assertFalse(locked)
        lock.releaseRead()
        time.sleep(1)
        self.assertTrue(locked)

        lock.acquireRead()

        def another_thread3():
            nonlocal locked

            lock.acquireRead()
            lock.acquireWrite()
            locked = True
            lock.releaseWrite()
            lock.releaseRead()

        locked = False
        threading.Thread(target=another_thread3).start()
        time.sleep(1)
        self.assertFalse(locked)
        lock.releaseRead()
        time.sleep(1)
        self.assertTrue(locked)
