import unittest
import hex.hexwidget as hexwidget
import hex.hexcolumn as hexcolumn
import hex.charcolumn as charcolumn
import hex.addresscolumn as addresscolumn
import hex.valuecodecs as valuecodecs
import hex.formatters as formatters
import hex.encodings as encodings
import hex.documents as documents
from PyQt4.QtCore import Qt
from PyQt4.QtGui import QFont, qApp
from PyQt4.QtTest import QTest


class TestHexWidget(unittest.TestCase):
    def test(self):
        ed = documents.Document(documents.deviceFromData(b'1234567890' * 1000))
        hw = hexwidget.HexWidget(None, ed)
        hw.clearColumns()

        hexColumnModel = hexcolumn.HexColumnModel(ed, valuecodecs.IntegerCodec(valuecodecs.IntegerCodec.Format16Bit),
                                                  formatters.IntegerFormatter(base=16))
        hw.appendColumn(hexColumnModel)
        charColumnModel = charcolumn.CharColumnModel(ed, encodings.getCodec('Windows-1251'), QFont())
        hw.appendColumn(charColumnModel)

        self.assertEqual(hw.leadingColumn.dataModel, hexColumnModel)

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
        ed.insertSpan(3, documents.FillSpan(5, b'\x00'))
        self.assertEqual(r.startPosition, 15)
        self.assertEqual(r.size, 1)

        ed.undo()

        hw.caretPosition = 10
        self.assertEqual(hw.caretPosition, 10)
        self.assertEqual(hw.caretIndex(hw.leadingColumn), hexColumnModel.indexFromPosition(10))

        index = hw.caretIndex(hw.leadingColumn)
        self.assertEqual(index.data(hexwidget.ColumnModel.DocumentDataRole), b'12')
        self.assertEqual(index.data(Qt.DisplayRole), ' 3231')
        self.assertEqual(index.data(Qt.EditRole), '+3231')
        self.assertEqual(index.data(hexwidget.ColumnModel.DocumentPositionRole), 10)
        self.assertEqual(index.data(hexwidget.ColumnModel.DataSizeRole), 2)

        hw.beginEditIndex()
        self.assertEqual(hw.editingIndex, index)
        QTest.keyClick(hw.view, Qt.Key_Escape)
        self.assertFalse(hw.editingIndex)
        self.assertEqual(index.data(), ' 3231')

        hw.beginEditIndex()
        QTest.keyClicks(hw.view, 'f')
        self.assertEqual(hw.editingIndex, hexColumnModel.indexFromPosition(10))
        self.assertEqual(hw.editingIndex.data(), '+3231')  # index value will remain the same, because +f321 is invalid
        QTest.keyClick(hw.view, Qt.Key_Enter)
        self.assertFalse(hw.editingIndex)
        self.assertEqual(hexColumnModel.indexFromPosition(10).data(), ' 3231')

        hw.beginEditIndex()
        QTest.keyClicks(hw.view, '0')
        self.assertEqual(hw.editingIndex, hexColumnModel.indexFromPosition(10))
        self.assertEqual(hw.editingIndex.data(), '+0231')
        QTest.keyClick(hw.view, Qt.Key_Enter)
        self.assertFalse(hw.editingIndex)
        self.assertEqual(hexColumnModel.indexFromPosition(10).data(), '  231') # no padding on column, btw)

        hw.deleteLater()
