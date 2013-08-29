import unittest
import hex.hexwidget as hexwidget
import hex.hexcolumn as hexcolumn
import hex.charcolumn as charcolumn
import hex.addresscolumn as addresscolumn
import hex.valuecodecs as valuecodecs
import hex.formatters as formatters
import hex.encodings as encodings
import hex.documents as documents
import hex.utils as utils
from PyQt4.QtCore import Qt
from PyQt4.QtGui import QFont, qApp
from PyQt4.QtTest import QTest


class TestHexWidget(unittest.TestCase):
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
        self.w.addSelection(hexwidget.Selection(utils.IndexRange(self.w.leadingColumn.dataModel,
                                                                 self.w.leadingColumn.dataModel.indexFromPosition(10),
                                                                 2)))
        QTest.keyPress(self.w.view, Qt.Key_Delete)
        self.assertEqual(self.w.document.length, length - 2)
