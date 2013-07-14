from PyQt4.QtCore import Qt
from PyQt4.QtGui import QVBoxLayout, QDialogButtonBox, QLabel, QPushButton, QMessageBox
import hex.utils as utils
import hex.hexlineedit as hexlineedit
import hex.matchers as matchers
import hex.hexwidget as hexwidget
import threading


class SearchDialog(utils.Dialog):
    def __init__(self, parent, hex_widget):
        utils.Dialog.__init__(self, parent, name='search_dialog')
        self.hexWidget = hex_widget

        self.setWindowTitle(utils.tr('Search'))

        self.m_layout = QVBoxLayout()
        self.setLayout(self.m_layout)
        self.descLabel = QLabel(self)
        self.descLabel.setText(utils.tr('Enter hex values to search for:'))
        self.m_layout.addWidget(self.descLabel)
        self.hexInput = hexlineedit.HexLineEdit(self)
        self.m_layout.addWidget(self.hexInput)
        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.addButton(QDialogButtonBox.Close)
        self.searchButton = QPushButton(utils.tr('Search'), self)
        self.searchButton.setIcon(utils.getIcon('edit-find'))
        self.searchButton.clicked.connect(self.doSearch)
        self.buttonBox.addButton(self.searchButton, QDialogButtonBox.ActionRole)
        self.buttonBox.rejected.connect(self.reject)
        self.m_layout.addWidget(self.buttonBox)

    def doSearch(self):
        self.searchButton.setEnabled(False)
        self.matcher = matchers.BinaryMatcher(self.hexWidget.editor, self.hexInput.data)
        self.matcher.newMatch.connect(self._onMatch, Qt.QueuedConnection)
        self.matcher.completed.connect(self._onCompleted, Qt.QueuedConnection)
        self.matcher.matchLimit = 1
        threading.Thread(target=self.matcher.findMatches).start()

    def _onMatch(self, match):
        self.hexWidget.emphasize(hexwidget.EmphasizedRange(self.hexWidget, match.position, match.length,
                                                        hexwidget.DataRange.UnitBytes))
        self.hexWidget.selectionRanges = [hexwidget.SelectionRange(self.hexWidget, match.position, match.length,
                                                              hexwidget.DataRange.UnitBytes)]

    def _onCompleted(self):
        if not self.matcher.allMatches:
            QMessageBox.information(self, utils.tr('Search'), utils.tr('Nothing had been found'))
        self.accept()
