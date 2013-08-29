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
        self.assertEqual(hw.selectionRanges[0].size, ed.length)

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

        hw.deleteLater()

    @classmethod
    def setUpClass(cls):
        data = bytes('Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor '
                     'incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud '
                     'exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute '
                     'irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla '
                     'pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui '
                     'officia deserunt mollit anim id est laborum.', encoding='ascii')

        dev = documents.deviceFromData(data)
        doc = documents.Document(dev)
        cls.w = hexwidget.HexWidget(None, doc)

    def test_set_caret_position(self):
        self.w.caretPosition = 20
        self.assertEqual(self.w.caretPosition, 20)

        self.w.caretPosition = 0
        self.assertEqual(self.w.caretPosition, 0)

    def test_set_negative_caret_position(self):
        self.w.caretPosition = -20
        self.assertEqual(self.w.caretPosition, 0)

    def test_nav_end(self):
        self.w.caretPosition = 0
        QTest.keyPress(self.w.view, Qt.Key_End)
        self.assertEqual(self.w.caretPosition, 15)

    def test_nav_home(self):
        self.w.caretPosition = 5
        QTest.keyPress(self.w.view, Qt.Key_Home)
        self.assertEqual(self.w.caretPosition, 0)

    def test_nav_pagedown(self):
        self.w.caretPosition = 0
        QTest.keyPress(self.w.view, Qt.Key_PageDown)
        self.assertEqual(self.w.leadingColumn.firstVisibleRow, 0)
        self.assertEqual(self.w.caretPosition, self.w.leadingColumn.lastFullVisibleRow * 16)

        QTest.keyPress(self.w.view, Qt.Key_PageUp)
        self.assertEqual(self.w.leadingColumn.firstVisibleRow, 0)
        self.assertEqual(self.w.caretPosition, 0)

    def test_delete(self):
        length = self.w.document.length
        self.w.addSelectionRange(hexwidget.SelectionRange(self.w, start=self.w.leadingColumn.dataModel.indexFromPosition(10),
                                                          length=2, unit=hexwidget.DataRange.UnitCells))
        QTest.keyPress(self.w.view, Qt.Key_Delete)
        self.assertEqual(self.w.document.length, length - 2)
