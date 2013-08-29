import unittest
import hex.utils as utils
from PyQt4.QtCore import QObject, pyqtSignal


class DocumentMock(QObject):
    bytesRemoved = pyqtSignal(object, object)
    bytesInserted = pyqtSignal(object, object)
    dataChanged = pyqtSignal(object, object)

    def length(self):
        return 0x1000


class DocumentRangeTest(unittest.TestCase):
    document = DocumentMock()

    def test_initial(self):
        r = utils.DocumentRange(self.document, 10, 0x2000)
        self.assertEqual(r.startPosition, 10)
        self.assertEqual(r.size, 0x2000)

    def test_insert(self):
        data = (
            (5, 10, 20, 10),
            (20, 10, 10, 10),
            (10, 10, 10, 20),
            (11, 200, 10, 210),
            (19, 100, 10, 110)
        )

        for d in data:
            r = utils.DocumentRange(self.document, 10, 10, fixed=False, allow_resize=True)
            self.document.bytesInserted.emit(d[0], d[1])
            self.assertEqual(r.startPosition, d[2])
            self.assertEqual(r.size, d[3])

    def test_remove(self):
        data = (
            (5, 5, 5, 10),
            (0, 10, 0, 10),
            (0, 15, 0, 5),
            (2, 100, 2, 0),
            (11, 2, 10, 8),
            (11, 100, 10, 1),
            (20, 10, 10, 10),
            (19, 1, 10, 9)
        )

        for d in data:
            r = utils.DocumentRange(self.document, 10, 10, fixed=False, allow_resize=True)
            self.document.bytesRemoved.emit(d[0], d[1])
            self.assertEqual(r.startPosition, d[2])
            self.assertEqual(r.size, d[3])

    def test_data_update(self):
        data = (
            (0, 1, False),
            (2, 7, False),
            (2, 10, True),
            (10, 10, True),
            (10, 1, True),
            (11, 10, True),
            (0, 100, True),
            (20, 1, False)
        )

        for d in data:
            r = utils.DocumentRange(self.document, 10, 10)
            signal_emitted = False
            def mark_emitted():
                nonlocal signal_emitted
                signal_emitted = True
            r.dataChanged.connect(mark_emitted)
            self.document.dataChanged.emit(d[0], d[1])
            self.assertEqual(signal_emitted, d[2])
