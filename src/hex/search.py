import threading
from PyQt4.QtCore import Qt, QAbstractListModel, QModelIndex
from PyQt4.QtGui import QVBoxLayout, QHBoxLayout, QDialogButtonBox, QLabel, QPushButton, QMessageBox, QWidget, QTreeView, \
                        QSizePolicy, qApp
import hex.utils as utils
import hex.hexlineedit as hexlineedit
import hex.matchers as matchers
import hex.hexwidget as hexwidget
import hex.operations as operations


class SearchDialog(utils.Dialog):
    def __init__(self, main_win, hex_widget):
        utils.Dialog.__init__(self, main_win, name='search_dialog')
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
        self.parentWidget().dockSearch.newSearch(self.hexWidget, self.matcher)
        self.matcher.run()
        self.accept()


class SearchResultsWidget(QWidget):
    def __init__(self, parent, hex_widget=None, matcher=None):
        QWidget.__init__(self, parent)
        self._matcher = matcher
        self.hexWidget = hex_widget

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.model = SearchResultsModel(self.hexWidget, None)
        self.resultsView = QTreeView(self)
        self.resultsView.setModel(self.model)
        self.resultsView.clicked.connect(self._onResultClicked)
        self.layout().addWidget(self.resultsView)

        self.progressTextLabel = operations.OperationProgressTextLabel(self, self._matcher)
        self.progressTextLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.searchCancelButton = operations.OperationCancelPushButton(self, self._matcher)

        hl = QHBoxLayout()
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self.progressTextLabel)
        hl.addWidget(self.searchCancelButton)
        self.layout().addLayout(hl)

        self.matcher = matcher

    @property
    def matcher(self):
        return self._matcher

    @matcher.setter
    def matcher(self, matcher):
        self._matcher = matcher
        self.model = SearchResultsModel(self.hexWidget, matcher)
        self.resultsView.setModel(self.model)
        self.searchCancelButton.operation = matcher
        self.progressTextLabel.operation = matcher

    def _onResultClicked(self, index):
        if index.isValid():
            rng = index.data(SearchResultsModel.MatchRangeRole)
            self.hexWidget.emphasize(hexwidget.EmphasizedRange(self.hexWidget, rng.startPosition, rng.size,
                                                                hexwidget.DataRange.UnitBytes))
            self.hexWidget.selectionRanges = [hexwidget.SelectionRange(self.hexWidget, rng.startPosition, rng.size,
                                                                        hexwidget.DataRange.UnitBytes)]


class SearchResultsModel(QAbstractListModel):
    MatchRangeRole, MatchRole = Qt.UserRole, Qt.UserRole + 1

    def __init__(self, hex_widget, matcher):
        QAbstractListModel.__init__(self)
        self._lock = threading.RLock()
        self._newResults = []
        self._matcher = matcher
        self._hexWidget = hex_widget
        self._results = []
        if self._matcher is not None:
            with self._matcher.lock:
                self._matcher.newResult.connect(self._onNewMatch, Qt.DirectConnection)
                self._matcher.finished.connect(self._onMatchFinished, Qt.QueuedConnection)

                for match in self._matcher.state.results.values():
                    self._results.append((match, self._createRange(match)))
        self.startTimer(400)

    def rowCount(self, index=QModelIndex()):
        return len(self._results) if not index.isValid() else 0

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and (0 <= index.row() < len(self._results)) and index.column() == 0:
            if role == Qt.DisplayRole or role == Qt.EditRole:
                rng = self._results[index.row()][1]
                return utils.tr('Matched {0:#x} bytes at position {1:#x}').format(rng.size, rng.startPosition)
            elif role == self.MatchRangeRole:
                return self._results[index.row()][1]
            elif role == self.MatchRole:
                return self._results[index.row()][0]
            elif role == Qt.ForegroundRole and not self._results[index.row()][1].size:
                return Qt.red

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        return None

    def _onNewMatch(self, result_name, match):
        with self._lock:
            self._newResults.append(match)

    def timerEvent(self, event):
        has_results = False
        with self._lock:
            if self._newResults:
                self.beginInsertRows(QModelIndex(), len(self._results), len(self._results) + len(self._newResults) - 1)
                self._results += ((match, self._createRange(match)) for match in self._newResults)
                self._newResults = []
                has_results = True
        if has_results:
            self.endInsertRows()

    def _onMatchFinished(self, final_status):
        pass

    def _onRangeUpdated(self):
        for row_index in range(len(self._results)):
            if self._results[row_index][1] is self.sender():
                index = self.index(row_index, 0)
                self.dataChanged.emit(index, index)
                break

    def _createRange(self, match):
        match_range = hexwidget.DataRange(self._hexWidget, match.position, match.length, hexwidget.DataRange.UnitBytes)
        match_range.updated.connect(self._onRangeUpdated)
        return match_range
