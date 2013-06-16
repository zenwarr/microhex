from PyQt4.QtCore import QFileInfo
from PyQt4.QtGui import QDialog
from hex.forms.ui_loadfiledialog import Ui_LoadFileDialog
import hex.utils as utils
import hex.formatters as formatters
import hex.settings as settings


globalSettings = settings.globalSettings()


class LoadFileDialog(QDialog):
    def __init__(self, parent, filename):
        QDialog.__init__(self, parent)
        self.ui = Ui_LoadFileDialog()
        self.ui.setupUi(self)
        self.filename = filename
        self.fileSize = QFileInfo(filename).size()
        self._userFreezeSize = self.ui.chkFreezeSize.isChecked()

        self.setWindowTitle(utils.tr('Load options for {0}').format(QFileInfo(filename).fileName()))

        self.ui.rangeStart.maximum = self.fileSize
        self.ui.rangeStart.number = 0
        self.ui.rangeStart.numberChanged.connect(self._onRangeStartChanged)
        self.ui.rangeLength.maximum = self.fileSize
        self.ui.rangeLength.number = self.fileSize
        self.ui.rangeLength.numberChanged.connect(self._updateLoadSize)
        self.ui.chkLoadRange.toggled.connect(self._onLoadRangeChecked)
        self.ui.chkFreezeSize.toggled.connect(self._onFreezeSizeChecked)

        self._maxMemoryLoadSize = globalSettings['files.max_memoryload_size']
        self.ui.chkMemoryLoad.setText(utils.tr('Completely read into memory (up to {0})').format(
                        utils.formatSize(self._maxMemoryLoadSize)))

        self._updateLoadSize()

    def _onRangeStartChanged(self, new_start):
        self.ui.rangeLength.maximum = self.fileSize - new_start

    def _updateLoadSize(self):
        load_size = self.ui.rangeLength.number if self.ui.chkLoadRange.isChecked() else self.fileSize
        self.ui.lblLoadSize.setText(utils.tr('{0} to be loaded').format(utils.formatSize(load_size)))
        self.ui.chkMemoryLoad.setEnabled(load_size <= self._maxMemoryLoadSize)

    def _onLoadRangeChecked(self):
        stored_freeze_size = self._userFreezeSize
        try:
            if self.ui.chkLoadRange.isChecked():
                self.ui.chkFreezeSize.setChecked(True)
            elif not self._userFreezeSize:
                self.ui.chkFreezeSize.setChecked(False)
        finally:
            self._userFreezeSize = stored_freeze_size

    def _onFreezeSizeChecked(self, is_checked):
        self._userFreezeSize = is_checked

    @property
    def loadOptions(self):
        from hex.files import FileLoadOptions

        options = FileLoadOptions()
        if self.ui.chkLoadRange.isChecked():
            options.range = self.ui.rangeStart.number, self.ui.rangeLength.number
        options.readOnly = self.ui.chkReadOnly.isChecked()
        options.freezeSize = self.ui.chkFreezeSize.isChecked()
        options.memoryLoad = self.ui.chkMemoryLoad.isEnabled() and self.ui.chkMemoryLoad.isChecked()

        return options
