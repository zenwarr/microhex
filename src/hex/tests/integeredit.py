import unittest
from hex.integeredit import IntegerEdit


class IntegerEditTest(unittest.TestCase):
    def test(self):
        widget = IntegerEdit(None)
        widget.resize(widget.sizeHint().height(), widget.width())
        self.doTestWidget(widget)
        widget.deleteLater()

    def doTestWidget(self, widget):
        self.assertEqual(widget.number, 0)

        self.assertEqual(widget.minimum, 0)
        self.assertEqual(widget.maximum, -1)

        widget.number = 100
        self.assertEqual(widget.number, 100)

        widget.stepBy(1)
        self.assertEqual(widget.number, 101)

        widget.maximum = 50
        self.assertEqual(widget.maximum, 50)
        self.assertEqual(widget.number, 50)

        widget.stepBy(1)
        self.assertEqual(widget.number, 50)

        widget.number = 0
        self.assertEqual(widget.number, 0)

        widget.stepBy(-1)
        self.assertEqual(widget.number, 0)
