import unittest
from hex.bigintscrollbar import BigIntScrollBar
from PyQt4.QtCore import Qt


class ScrollBarTest(unittest.TestCase):
    def test(self):
        sbar = BigIntScrollBar(Qt.Horizontal, None)

        self.assertEqual(sbar.value, 0)
        self.assertEqual(sbar.maximum, 100)
        self.assertEqual(sbar.minimum, 0)

        sbar.value = 30
        self.assertEqual(sbar.value, 30)

        self.assertEqual(sbar._sbar.value(), 30)
        self.assertEqual(sbar._sbar.maximum(), 100)
        self.assertEqual(sbar._sbar.minimum(), 0)
        self.assertEqual(sbar._sbar.pageStep(), 10)

        sbar.value = 200
        self.assertEqual(sbar.value, 100)

        very_big = 0xffffffffffffffffffffffffffffffff ** 2
        big2 = 0xffffffffffff78b4

        sbar.maximum = very_big
        self.assertEqual(sbar.maximum, very_big)

        sbar.value = big2
        self.assertEqual(sbar.value, big2)

