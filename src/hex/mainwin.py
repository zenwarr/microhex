from PyQt4.QtCore import QFileInfo, Qt, QByteArray
from PyQt4.QtGui import QMainWindow, QTabWidget, QFileDialog, QKeySequence, QMdiSubWindow, QApplication, QProgressBar, \
                        QWidget, QVBoxLayout, QFileIconProvider, QApplication, QIcon
from hex.hexwidget import HexWidget
import hex.settings as settings
import hex.appsettings as appsettings
import hex.utils as utils
import hex.files as files
import hex.resources.qrc_main


def forActiveWidget(fn):
    def wrapped(self):
        if self.activeSubWidget is not None:
            return fn(self)
    return wrapped


globalSettings = settings.globalSettings()
globalQuickSettings = settings.globalQuickSettings()


class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self._inited = False

        self.setWindowTitle(QApplication.applicationName())
        self.setWindowIcon(QIcon(':/main/images/hex.png'))

        self.subWidgets = []
        self._activeSubWidget = None

        self.tabsWidget = QTabWidget(self)
        self.tabsWidget.setDocumentMode(True)
        self.tabsWidget.setTabsClosable(True)
        self.tabsWidget.setFocusPolicy(Qt.StrongFocus)
        self.tabsWidget.currentChanged.connect(self._onTabChanged)
        self.tabsWidget.tabCloseRequested.connect(self.closeTab)

        self.setCentralWidget(self.tabsWidget)
        self.setFocusProxy(self.tabsWidget)
        self.setFocus()

        QApplication.instance().focusChanged.connect(self._onGlobalFocusChanged)

        menubar = self.menuBar()
        
        self.fileMenu = menubar.addMenu(utils.tr('File'))
        self.actionOpenFile = self.fileMenu.addAction(utils.tr('Open file...'))
        self.actionOpenFile.setShortcut(QKeySequence('Ctrl+O'))
        self.actionOpenFile.triggered.connect(self.openFileDialog)
        self.fileMenu.addSeparator()
        self.actionCloseTab = self.fileMenu.addAction(utils.tr('Close'))
        self.actionCloseTab.setShortcut(QKeySequence('Ctrl+W'))
        self.actionCloseTab.triggered.connect(self.closeActiveTab)
        self.fileMenu.addSeparator()
        self.actionExit = self.fileMenu.addAction(utils.tr('Exit'))
        self.actionExit.triggered.connect(self.close)

        self.editMenu = menubar.addMenu(utils.tr('Edit'))
        self.actionUndo = self.editMenu.addAction(utils.tr('Undo'))
        self.actionUndo.setShortcut(QKeySequence('Ctrl+Z'))
        self.actionUndo.triggered.connect(self.undo)
        self.actionRedo = self.editMenu.addAction(utils.tr('Redo'))
        self.actionRedo.setShortcut(QKeySequence('Ctrl+Y'))
        self.actionRedo.triggered.connect(self.redo)
        self.editMenu.addSeparator()

        self.copyAction = self.editMenu.addAction(utils.tr('Copy'))
        self.copyAction.setShortcut(QKeySequence('Ctrl+C'))
        self.copyAction.triggered.connect(self.copy)
        self.pasteAction = self.editMenu.addAction(utils.tr('Paste'))
        self.pasteAction.setShortcut(QKeySequence('Ctrl+V'))
        self.pasteAction.triggered.connect(self.paste)
        self.editMenu.addSeparator()

        self.actionClearSelection = self.editMenu.addAction(utils.tr('Clear selection'))
        self.actionClearSelection.setShortcut(QKeySequence('Ctrl+D'))
        self.actionClearSelection.triggered.connect(self.clearSelection)
        self.actionSelectAll = self.editMenu.addAction(utils.tr('Select all'))
        self.actionSelectAll.setShortcut(QKeySequence('Ctrl+A'))
        self.actionSelectAll.triggered.connect(self.selectAll)

        self.editMenu.addSeparator()
        self.actionInsertMode = self.editMenu.addAction(utils.tr('Insert mode'))
        self.actionInsertMode.setCheckable(True)
        self.actionInsertMode.setShortcut(QKeySequence('Ins'))
        self.actionInsertMode.triggered.connect(self.setInsertMode)

        self.editMenu.addSeparator()
        self.actionRemoveSelected = self.editMenu.addAction(utils.tr('Remove selected'))
        self.actionRemoveSelected.setShortcut(QKeySequence('Del'))
        self.actionRemoveSelected.triggered.connect(self.removeSelected)

        self.actionFillZeros = self.editMenu.addAction(utils.tr('Fill selected with zeros'))
        self.actionFillZeros.triggered.connect(self.fillZeros)

        self.viewMenu = menubar.addMenu(utils.tr('View'))
        self.actionShowHeader = self.viewMenu.addAction(utils.tr('Show header'))
        self.actionShowHeader.triggered.connect(self.showHeader)
        self.actionShowHeader.setCheckable(True)

        self.toolsMenu = menubar.addMenu(utils.tr('Tools'))
        self.actionShowSettings = self.toolsMenu.addAction(utils.tr('Settings...'))
        self.actionShowSettings.triggered.connect(self.showSettings)

        self.helpMenu = menubar.addMenu(utils.tr('?'))
        self.actionAbout = self.helpMenu.addAction(utils.tr('About program...'))
        self.actionAbout.triggered.connect(self.showAbout)

        geom = globalQuickSettings['mainWindow.geometry']
        if geom and isinstance(geom, str):
            self.restoreGeometry(QByteArray.fromHex(geom))

    def showEvent(self, event):
        if not self._inited:
            self.openFile('/home/victor/Документы/utf-16.txt')
            self._inited = True

    def closeEvent(self, event):
        while self.tabsWidget.count():
            if not self.closeTab(0):
                event.ignore()
                return

        globalQuickSettings['mainWindow.geometry'] = str(self.saveGeometry().toHex(), encoding='ascii')

    def closeActiveTab(self):
        self.closeTab(self.tabsWidget.currentIndex())

    def closeTab(self, tab_index):
        subWidget = self.tabsWidget.widget(tab_index)
        self.tabsWidget.removeTab(tab_index)
        self.subWidgets = [w for w in self.subWidgets if w is not subWidget]
        return True

    def openFileDialog(self):
        from hex.loadfiledialog import LoadFileDialog

        filename = QFileDialog.getOpenFileName(self, utils.tr('Open file'), utils.lastFileDialogPath())
        if filename:
            utils.setLastFileDialogPath(filename)

            load_dialog = LoadFileDialog(self, filename)
            if load_dialog.exec_() == LoadFileDialog.Accepted:
                self.openFile(filename, load_dialog.loadOptions)

    def openFile(self, filename, load_options=None):
        subWidget = HexSubWindow(self, filename, files.editorFromFile(filename, load_options))
        icon_provider = QFileIconProvider()
        self.tabsWidget.addTab(subWidget, icon_provider.icon(QFileInfo(filename)), QFileInfo(filename).fileName())
        self.subWidgets.append(subWidget)
        self.tabsWidget.setCurrentWidget(subWidget)

    def _onTabChanged(self, tab_index):
        oldSubWidget = self._activeSubWidget

        subWidget = self.tabsWidget.widget(tab_index)
        if subWidget is not None and hasattr(subWidget, 'path'):
            self.setWindowTitle('')
            self.setWindowFilePath(subWidget.path)
        else:
            self.setWindowTitle(QApplication.applicationName())
        if subWidget is not None:
            subWidget.setFocus()

        self._activeSubWidget = subWidget

        self.actionShowHeader.setEnabled(subWidget is not None)
        self.actionShowHeader.setChecked(subWidget is not None and subWidget.hexWidget.showHeader)

        self.actionInsertMode.setEnabled(subWidget is not None)
        self.actionInsertMode.setChecked(subWidget is not None and subWidget.hexWidget.insertMode)
        if oldSubWidget is not None:
            oldSubWidget.hexWidget.insertModeChanged.disconnect(self._onInsertModeChanged)
        if subWidget is not None:
            subWidget.hexWidget.insertModeChanged.connect(self._onInsertModeChanged)

    def _onGlobalFocusChanged(self, old, new):
        # check if this widget is child of self.tabsWidget
        if not isinstance(new, (HexSubWindow, HexWidget)):
            widget = new
            while widget is not None:
                if widget is self.tabsWidget:
                    if self.tabsWidget.currentWidget() is not None:
                        self.tabsWidget.currentWidget().setFocus()
                    break
                widget = widget.parentWidget()

    @property
    def activeSubWidget(self):
        return self.tabsWidget.currentWidget()

    @forActiveWidget
    def clearSelection(self):
        self.activeSubWidget.hexWidget.clearSelection()

    @forActiveWidget
    def selectAll(self):
        self.activeSubWidget.hexWidget.selectAll()

    @forActiveWidget
    def copy(self):
        self.activeSubWidget.hexWidget.copy()

    @forActiveWidget
    def paste(self):
        self.activeSubWidget.hexWidget.paste()

    @forActiveWidget
    def undo(self):
        self.activeSubWidget.hexWidget.undo()

    @forActiveWidget
    def redo(self):
        self.activeSubWidget.hexWidget.redo()

    def showAbout(self):
        from hex.aboutdialog import AboutDialog

        dlg = AboutDialog(self)
        dlg.exec_()

    def showHeader(self, show):
        if self.activeSubWidget:
            self.activeSubWidget.hexWidget.showHeader = show
            self.actionShowHeader.setChecked(show)

    def showSettings(self):
        from hex.settingsdialog import SettingsDialog

        dlg = SettingsDialog(self)
        dlg.exec_()

    def setInsertMode(self, mode):
        if self.activeSubWidget:
            self.activeSubWidget.hexWidget.insertMode = mode

    def _onInsertModeChanged(self, mode):
        self.actionInsertMode.setChecked(mode)

    @forActiveWidget
    def removeSelected(self):
        self.activeSubWidget.hexWidget.removeSelected()

    @forActiveWidget
    def fillZeros(self):
        self.activeSubWidget.hexWidget.fillSelected(b'\x00')


class HexSubWindow(QWidget):
    def __init__(self, parent, filename, editor):
        QWidget.__init__(self, parent)
        self.path = QFileInfo(filename).fileName()
        self.hexWidget = HexWidget(self, editor)
        self.hexWidget.loadSettings(globalSettings)
        self.setFocusProxy(self.hexWidget)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.hexWidget)
