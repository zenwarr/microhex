from PyQt4.QtCore import QFileInfo, QSize
from hex.forms.ui_loadfiledialog import Ui_LoadFileDialog
import hex.utils as utils
import hex.formatters as formatters
import hex.settings as settings
import hex.appsettings as appsettings
import hex.documents as documents


globalSettings = settings.globalSettings()


class LoadFileDialog(utils.Dialog):
    def __init__(self, parent, filename, load_options=None):
        utils.Dialog.__init__(self, parent, name='load_file_dialog')
        self.ui = Ui_LoadFileDialog()
        self.ui.setupUi(self)
        self.loadGeometry()

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

        self._updateLoadSize()

        if load_options is not None:
            self.ui.chkReadOnly.setChecked(load_options.readOnly)
            self.ui.chkFreezeSize.setChecked(load_options.freezeSize)
            self.ui.chkMemoryLoad.setChecked(load_options.memoryLoad)
            self.ui.chkLoadRange.setChecked(load_options.rangeLoad)
            if load_options.rangeLoad:
                self.ui.rangeStart.number = load_options.rangeStart
                self.ui.rangeLength.number = load_options.rangeLength

        self.setMaximumHeight(self.minimumHeight())

    def _onRangeStartChanged(self, new_start):
        self.ui.rangeLength.maximum = self.fileSize - new_start

    def _updateLoadSize(self):
        load_size = self.ui.rangeLength.number if self.ui.chkLoadRange.isChecked() else self.fileSize
        self.ui.lblLoadSize.setText(utils.tr('{0} to be loaded').format(utils.formatSize(load_size)))

    def _onLoadRangeChecked(self):
        stored_freeze_size = self._userFreezeSize
        try:
            self.ui.chkFreezeSize.setEnabled(not self.ui.chkLoadRange.isChecked())
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
        options = documents.FileLoadOptions()
        if self.ui.chkLoadRange.isChecked():
            options.rangeLoad = True
            options.rangeStart = self.ui.rangeStart.number
            options.rangeLength = self.ui.rangeLength.number
        options.readOnly = self.ui.chkReadOnly.isChecked()
        options.freezeSize = self.ui.chkFreezeSize.isChecked()
        options.memoryLoad = self.ui.chkMemoryLoad.isEnabled() and self.ui.chkMemoryLoad.isChecked()

        return options
