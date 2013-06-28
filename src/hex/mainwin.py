from PyQt4.QtCore import QFileInfo, Qt, QByteArray, QObject, pyqtSignal
from PyQt4.QtGui import QMainWindow, QTabWidget, QFileDialog, QKeySequence, QMdiSubWindow, QApplication, QProgressBar, \
                        QWidget, QVBoxLayout, QFileIconProvider, QApplication, QIcon, QDialog, QAction, QIcon
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
    activeSubWidgetChanged = pyqtSignal(object)

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

        self.createActions()
        self.buildMenus()

        geom = globalQuickSettings['mainWindow.geometry']
        if geom and isinstance(geom, str):
            self.restoreGeometry(QByteArray.fromHex(geom))

    def createActions(self):
        self.actionOpenFile = QAction(QIcon.fromTheme('document-open'), utils.tr('Open file...'), None)
        self.actionOpenFile.setShortcut(QKeySequence('Ctrl+O'))
        self.actionOpenFile.triggered.connect(self.openFileDialog)

        self.actionCloseTab = ObservingAction(QIcon(), utils.tr('Close'), PropertyObserver(self, 'activeSubWidget'))
        self.actionCloseTab.setShortcut(QKeySequence('Ctrl+W'))
        self.actionCloseTab.triggered.connect(self.closeActiveTab)
        
        self.actionExit = QAction(QIcon.fromTheme('application-exit'), utils.tr('Exit'), None)
        self.actionExit.triggered.connect(self.close)

        self.actionUndo = ObservingAction(QIcon.fromTheme('edit-undo'), utils.tr('Undo'),
                                          PropertyObserver(self, 'activeSubWidget.hexWidget.canUndo'))
        self.actionUndo.setShortcut(QKeySequence('Ctrl+Z'))
        self.actionUndo.triggered.connect(self.undo)

        self.actionRedo = ObservingAction(QIcon.fromTheme('edit-redo'), utils.tr('Redo'),
                                          PropertyObserver(self, 'activeSubWidget.hexWidget.canRedo'))
        self.actionRedo.setShortcut(QKeySequence('Ctrl+Y'))
        self.actionRedo.triggered.connect(self.redo)

        self.actionCopy = ObservingAction(QIcon.fromTheme('edit-copy'), utils.tr('Copy'),
                                          PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionCopy.setShortcut(QKeySequence('Ctrl+C'))
        self.actionCopy.triggered.connect(self.copy)

        self.actionPaste = ObservingAction(QIcon.fromTheme('edit-paste'), utils.tr('Paste'),
                                           PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionPaste.setShortcut(QKeySequence('Ctrl+V'))
        self.actionPaste.triggered.connect(self.paste)

        self.actionClearSelection = ObservingAction(QIcon(), utils.tr('Clear selection'),
                                                    PropertyObserver(self, 'activeSubWidget.hexWidget.hasSelection'))
        self.actionClearSelection.setShortcut(QKeySequence('Ctrl+D'))
        self.actionClearSelection.triggered.connect(self.clearSelection)

        self.actionSelectAll = ObservingAction(QIcon.fromTheme('edit-select-all'), utils.tr('Select all'),
                                               PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionSelectAll.setShortcut(QKeySequence('Ctrl+A'))
        self.actionSelectAll.triggered.connect(self.selectAll)

        self.actionInsertMode = ObservingAction(QIcon(), utils.tr('Insert mode'),
                                                PropertyObserver(self, 'activeSubWidget.hexWidget'),
                                                PropertyObserver(self, 'activeSubWidget.hexWidget.insertMode'))
        self.actionInsertMode.setShortcut(QKeySequence('Ins'))
        self.actionInsertMode.triggered.connect(self.setInsertMode)

        self.actionRemoveSelected = ObservingAction(QIcon.fromTheme('edit-delete'), utils.tr('Remove selected'),
                                                    PropertyObserver(self, 'activeSubWidget.hexWidget.hasSelection'))
        self.actionRemoveSelected.setShortcut(QKeySequence('Del'))
        self.actionRemoveSelected.triggered.connect(self.removeSelected)

        self.actionFillZeros = ObservingAction(QIcon(), utils.tr('Fill selected with zeros'),
                                               PropertyObserver(self, 'activeSubWidget.hexWidget.hasSelection'))
        self.actionFillZeros.triggered.connect(self.fillZeros)

        self.actionShowHeader = ObservingAction(QIcon(), utils.tr('Show header'),
                                                PropertyObserver(self, 'activeSubWidget.hexWidget'),
                                                PropertyObserver(self, 'activeSubWidget.hexWidget.showHeader'))
        self.actionShowHeader.triggered.connect(self.showHeader)
        self.actionShowHeader.setCheckable(True)

        self.actionSetupColumn = ObservingAction(QIcon(), utils.tr('Setup column...'),
                                                 PropertyObserver(self, 'activeSubWidget.hexWidget.leadingColumn'))
        self.actionSetupColumn.triggered.connect(self.setupActiveColumn)

        self.actionAddColumn = ObservingAction(QIcon(), utils.tr('Add column...'),
                                               PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionAddColumn.triggered.connect(self.addColumn)

        self.actionRemoveColumn = ObservingAction(QIcon(), utils.tr('Remove column'),
                                                  PropertyObserver(self, 'activeSubWidget.hexWidget.leadingColumn'))
        self.actionRemoveColumn.triggered.connect(self.removeColumn)

        self.actionAddAddress = ObservingAction(QIcon(), utils.tr('Add address bar to column...'),
                                                 PropertyObserver(self, 'activeSubWidget.hexWidget.leadingColumn'))
        self.actionAddAddress.triggered.connect(self.addAddressColumn)

        self.actionShowSettings = QAction(QIcon(), utils.tr('Settings...'), None)
        self.actionShowSettings.triggered.connect(self.showSettings)

        self.actionAbout = QAction(QIcon.fromTheme('help-about'), utils.tr('About program...'), None)
        self.actionAbout.triggered.connect(self.showAbout)

    def buildMenus(self):
        menubar = self.menuBar()
        self.fileMenu = menubar.addMenu(utils.tr('File'))
        self.fileMenu.addAction(self.actionOpenFile)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.actionCloseTab)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.actionExit)

        self.editMenu = menubar.addMenu(utils.tr('Edit'))
        self.editMenu.addAction(self.actionUndo)
        self.editMenu.addAction(self.actionRedo)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.actionCopy)
        self.editMenu.addAction(self.actionPaste)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.actionClearSelection)
        self.editMenu.addAction(self.actionSelectAll)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.actionInsertMode)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.actionRemoveSelected)
        self.editMenu.addAction(self.actionFillZeros)

        self.viewMenu = menubar.addMenu(utils.tr('View'))
        self.viewMenu.addAction(self.actionShowHeader)
        self.viewMenu.addSeparator()
        self.viewMenu.addAction(self.actionSetupColumn)
        self.viewMenu.addAction(self.actionAddColumn)
        self.viewMenu.addAction(self.actionRemoveColumn)
        self.viewMenu.addAction(self.actionAddAddress)

        self.toolsMenu = menubar.addMenu(utils.tr('Tools'))
        self.toolsMenu.addAction(self.actionShowSettings)

        self.helpMenu = menubar.addMenu(utils.tr('?'))
        self.helpMenu.addAction(self.actionAbout)

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
        subWidget = self.tabsWidget.widget(tab_index)
        if subWidget is not None and hasattr(subWidget, 'path'):
            self.setWindowTitle('')
            self.setWindowFilePath(subWidget.path)
        else:
            self.setWindowTitle(QApplication.applicationName())
        if subWidget is not None:
            subWidget.setFocus()

        self._activeSubWidget = subWidget
        self.activeSubWidgetChanged.emit(subWidget)

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

    def showSettings(self):
        from hex.settingsdialog import SettingsDialog

        dlg = SettingsDialog(self)
        dlg.exec_()

    def setInsertMode(self, mode):
        if self.activeSubWidget:
            self.activeSubWidget.hexWidget.insertMode = mode

    @forActiveWidget
    def removeSelected(self):
        self.activeSubWidget.hexWidget.removeSelected()

    @forActiveWidget
    def fillZeros(self):
        self.activeSubWidget.hexWidget.fillSelected(b'\x00')

    @forActiveWidget
    def setupActiveColumn(self):
        import hex.columnproviders as columnproviders
        active_column = self.activeSubWidget.hexWidget.leadingColumn
        if active_column is not None:
            dlg = columnproviders.ConfigureColumnDialog(self, self.activeSubWidget.hexWidget, active_column.sourceModel)
            dlg.exec_()

    @forActiveWidget
    def addColumn(self):
        import hex.columnproviders as columnproviders
        dlg = columnproviders.CreateColumnDialog(self, self.activeSubWidget.hexWidget)
        if dlg.exec_() == QDialog.Accepted:
            self.activeSubWidget.hexWidget.appendColumn(dlg.createColumnModel())

    @forActiveWidget
    def removeColumn(self):
        self.activeSubWidget.hexWidget.removeActiveColumn()

    @forActiveWidget
    def addAddressColumn(self):
        import hex.addresscolumn as addresscolumn

        hex_widget = self.activeSubWidget.hexWidget
        if hex_widget.leadingColumn is None:
            return

        dlg = addresscolumn.AddAddressColumnDialog(self, hex_widget, hex_widget.leadingColumn)
        if dlg.exec_() == QDialog.Accepted:
            dlg.addColumn()


class PropertyObserver(QObject):
    valueChanged = pyqtSignal(object)

    def __init__(self, parent, props):
        QObject.__init__(self)
        self.parent = parent
        self.props = props.split('.') if isinstance(props, str) else props
        self.value = None
        self._connectedSignals = []
        self._update()

    def _update(self):
        old_value = self.value
        self.value = None
        new_value = None
        for signal in self._connectedSignals:
            signal.disconnect(self._update)
        self._connectedSignals = []

        parent = self.parent
        for prop_name in self.props:
            if parent is None or not hasattr(parent, prop_name):
                break
            prop_value = getattr(parent, prop_name)
            if callable(prop_value):
                prop_value = prop_value()
            new_value = prop_value

            signal_name = prop_name + 'Changed'
            if hasattr(parent, signal_name):
                signal = getattr(parent, signal_name)
                if hasattr(signal, 'connect'):
                    signal.connect(self._update)
                    self._connectedSignals.append(signal)

            parent = prop_value

        self.value = new_value
        if old_value != self.value:
            self.valueChanged.emit(self.value)


class ObservingAction(QAction):
    def __init__(self, icon, text, enabled_observer=None, checked_observed=None):
        QAction.__init__(self, icon, text, None)
        self.enabledObserver = enabled_observer
        self.checkedObserver = checked_observed
        if enabled_observer is not None:
            enabled_observer.valueChanged.connect(lambda f: self.setEnabled(bool(f)))
            self.setEnabled(bool(enabled_observer.value))
        if checked_observed is not None:
            self.setCheckable(True)
            checked_observed.valueChanged.connect(lambda f: self.setChecked(bool(f)))
            self.setChecked(bool(checked_observed.value))


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
