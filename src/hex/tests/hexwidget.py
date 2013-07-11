import unittest
import hex.hexwidget as hexwidget
import hex.hexcolumn as hexcolumn
import hex.charcolumn as charcolumn
import hex.addresscolumn as addresscolumn
import hex.editor as editor
import hex.devices as devices
import hex.valuecodecs as valuecodecs
import hex.formatters as formatters
import hex.encodings as encodings
from PyQt4.QtGui import QFont


class TestHexWidget(unittest.TestCase):
    def test(self):
        ed = editor.Editor(devices.deviceFromBytes(b'1234567890' * 1000))
        hw = hexwidget.HexWidget(None, ed)

        hexColumnModel = hexcolumn.HexColumnModel(ed, valuecodecs.IntegerCodec(valuecodecs.IntegerCodec.Format16Bit),
                                                  formatters.IntegerFormatter(base=16))
        hw.appendColumn(hexColumnModel)
        charColumnModel = charcolumn.CharColumnModel(ed, encodings.getCodec('Windows-1251'), QFont())
        hw.appendColumn(charColumnModel)

        r = hexwidget.DataRange(hw, 10, 4, hexwidget.DataRange.UnitBytes)
        self.assertEqual(r.startPosition, 10)
        self.assertEqual(r.length, 4)
        self.assertEqual(r.size, 4)

        r = hexwidget.DataRange(hw, hexColumnModel.firstIndex, 4, hexwidget.DataRange.UnitCells)
        self.assertEqual(r.startPosition, 0)
        self.assertEqual(r.length, 4)
        self.assertEqual(r.size, 8)

        hw.selectAll()
        self.assertEqual(len(hw.selectionRanges), 1)
        self.assertEqual(hw.selectionRanges[0].startPosition, 0)
        self.assertEqual(hw.selectionRanges[0].size, len(ed))

        r = hexwidget.DataRange(hw, charColumnModel.indexFromOffset(10), 1, hexwidget.DataRange.UnitCells,
                                hexwidget.DataRange.BoundToData)
        ed.insertSpan(3, editor.FillSpan(ed, b'\x00', 5))
        self.assertEqual(r.startPosition, 15)
        self.assertEqual(r.size, 1)

        hw.deleteLater()
