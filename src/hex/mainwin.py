from PyQt4.QtCore import QFileInfo, Qt, QByteArray, QObject, pyqtSignal, QUrl
from PyQt4.QtGui import QMainWindow, QTabWidget, QFileDialog, QKeySequence, QMdiSubWindow, QApplication, QProgressBar, \
                        QWidget, QVBoxLayout, QFileIconProvider, QApplication, QIcon, QDialog, QAction, QIcon, QLabel, \
                        QMessageBox
from hex.hexwidget import HexWidget
import hex.settings as settings
import hex.appsettings as appsettings
import hex.utils as utils
import hex.devices as devices
import hex.editor as editor
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
        self.buildStatusbar()

        geom = globalQuickSettings['mainWindow.geometry']
        if geom and isinstance(geom, str):
            self.restoreGeometry(QByteArray.fromHex(geom))

    def createActions(self):
        self.actionCreateDocument = QAction(QIcon.fromTheme('document-new'), utils.tr('Create...'), None)
        self.actionCreateDocument.setShortcut(QKeySequence('Ctrl+N'))
        self.actionCreateDocument.triggered.connect(self.newDocument)

        self.actionOpenFile = QAction(QIcon.fromTheme('document-open'), utils.tr('Open file...'), None)
        self.actionOpenFile.setShortcut(QKeySequence('Ctrl+O'))
        self.actionOpenFile.triggered.connect(self.openFileDialog)

        self.actionSave = ObservingAction(QIcon.fromTheme('document-save'), utils.tr('Save'),
                                          PropertyObserver(self, 'activeSubWidget.hexWidget.isModified'))
        self.actionSave.setShortcut(QKeySequence('Ctrl+S'))
        self.actionSave.triggered.connect(self.save)

        self.actionSaveAs = ObservingAction(QIcon(), utils.tr('Save as...'),
                                            PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionSaveAs.setShortcut(QKeySequence('Ctrl+Shift+S'))
        self.actionSaveAs.triggered.connect(self.saveAs)

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
        self.fileMenu.addAction(self.actionCreateDocument)
        self.fileMenu.addAction(self.actionOpenFile)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.actionSave)
        self.fileMenu.addAction(self.actionSaveAs)
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

    def buildStatusbar(self):
        self.lblReadOnly = QLabel()

        def readonly_to_text(readonly):
            if readonly is not None:
                return utils.tr('Read-only') if readonly else utils.tr('Read-write')
            else:
                return ''

        self.readOnlyObserver = PropertyObserver(self, 'activeSubWidget.hexWidget.readOnly', readonly_to_text)
        self.readOnlyObserver.valueChanged.connect(self.lblReadOnly.setText)

        self.lblInsertMode = QLabel()

        def insertmode_to_text(insert_mode):
            if insert_mode is not None:
                return utils.tr('Insert') if insert_mode else utils.tr('Overwrite')
            else:
                return ''

        self.insertModeObserver = PropertyObserver(self, 'activeSubWidget.hexWidget.insertMode', insertmode_to_text)
        self.insertModeObserver.valueChanged.connect(self.lblInsertMode.setText)

        statusbar = self.statusBar()
        statusbar.addPermanentWidget(self.lblReadOnly)
        statusbar.addPermanentWidget(self.lblInsertMode)

    def showEvent(self, event):
        if not self._inited:
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
        if subWidget.hexWidget.isModified:
            msgbox = QMessageBox(self)
            msgbox.setWindowTitle(utils.tr('Close editor'))
            msgbox.setIcon(QMessageBox.Question)
            msgbox.setText(utils.tr('Document {0} has unsaved changed. Do you want to save it?')
                                        .format(subWidget.title))
            msgbox.addButton(utils.tr('Save'), QMessageBox.YesRole)
            msgbox.addButton(utils.tr('Do not save'), QMessageBox.NoRole)
            msgbox.addButton(QMessageBox.Cancel)
            msgbox.setDefaultButton(QMessageBox.Cancel)
            ans = msgbox.exec_()
            if ans == QMessageBox.Cancel:
                return
            elif ans == QMessageBox.Yes:
                subWidget.hexWidget.save()

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
        e = editor.Editor(devices.deviceFromUrl(QUrl.fromLocalFile(filename), load_options))
        subWidget = HexSubWindow(self, e)
        self._addTab(subWidget)

    @forActiveWidget
    def saveAs(self):
        url = self.activeSubWidget.hexWidget.editor.device.url
        filename = url.toLocalFile() if url.isLocalFile() else ''
        filename = QFileDialog.getSaveFileName(self, utils.tr('Save file as'), filename)
        if filename:
            options = devices.FileLoadOptions()
            options.forceNew = True
            save_device = devices.deviceFromUrl(QUrl.fromLocalFile(filename), options)
            self.activeSubWidget.hexWidget.save(save_device, switch_to_device=True)

    def newDocument(self):
        e = editor.Editor(devices.deviceFromBytes(QByteArray()))
        self._addTab(HexSubWindow(self, e, utils.tr('New document')))

    def _addTab(self, subWidget):
        self.tabsWidget.addTab(subWidget, subWidget.icon, subWidget.tabTitle)
        self.subWidgets.append(subWidget)
        self.tabsWidget.setCurrentWidget(subWidget)
        subWidget.titleChanged.connect(self._updateTabTitle)
        subWidget.isModifiedChanged.connect(self._onIsModifiedChanged)

    def _onTabChanged(self, tab_index):
        self._updateTitle()

        subWidget = self.tabsWidget.widget(tab_index)
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

    def _onIsModifiedChanged(self):
        if self.sender() is self.tabsWidget.currentWidget():
            self._updateTitle()

    def _updateTabTitle(self, new_title):
        tab_index = self.tabsWidget.indexOf(self.sender())
        self.tabsWidget.setTabText(tab_index, self.sender().tabTitle)
        if tab_index != -1 and tab_index == self.tabsWidget.currentIndex():
            self._updateTitle()

    def _updateTitle(self):
        subWidget = self.tabsWidget.currentWidget()
        if subWidget is not None:
            self.setWindowTitle('')
            self.setWindowFilePath(subWidget.title)
            self.setWindowModified(subWidget.hexWidget.isModified)
        else:
            self.setWindowTitle(QApplication.applicationName())

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

    @forActiveWidget
    def save(self):
        self.activeSubWidget.hexWidget.save()


class PropertyObserver(QObject):
    valueChanged = pyqtSignal(object)

    def __init__(self, parent, props, transform_function=None):
        QObject.__init__(self)
        self.parent = parent
        self.props = props.split('.') if isinstance(props, str) else props
        self.value = None
        self._connectedSignals = []
        self._realValue = None
        self._transformFunction = transform_function
        self._update()

    def _update(self):
        old_value = self.value
        self.value = None
        new_value = None
        for signal in self._connectedSignals:
            signal.disconnect(self._update)
        self._connectedSignals = []
        self._realValue = False

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
        else:
            self._realValue = True

        if not self._realValue:
            new_value = None

        self.value = new_value if self._transformFunction is None else self._transformFunction(new_value)
        if old_value != self.value:
            self.valueChanged.emit(self.value)

    @property
    def isRealValue(self):
        """True if self.value is real value of most nested property. When isRealValue is True, value is always None
        """
        return self._realValue


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
    titleChanged = pyqtSignal(str)
    isModifiedChanged = pyqtSignal(bool)

    def __init__(self, parent, editor, name=''):
        QWidget.__init__(self, parent)
        if editor.url.isLocalFile():
            self.icon = QFileIconProvider().icon(QFileInfo(editor.url.toLocalFile()))
        else:
            self.icon = QIcon()
        self.name = name
        self.hexWidget = HexWidget(self, editor)
        self.hexWidget.loadSettings(globalSettings)
        self.hexWidget.isModifiedChanged.connect(self._onModifiedChanged)
        self.hexWidget.urlChanged.connect(self._onUrlChanged)
        self.setFocusProxy(self.hexWidget)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.hexWidget)

    @property
    def title(self):
        name = self.name
        if self.hexWidget.url.isLocalFile():
            name = self.hexWidget.url.toLocalFile()
        return name

    @property
    def tabTitle(self):
        return self.title + ('* ' * self.hexWidget.isModified)

    @property
    def isModified(self):
        return self.hexWidget.isModified

    def _onModifiedChanged(self, is_modified):
        self.isModifiedChanged.emit(is_modified)
        self.titleChanged.emit(self.title)

    def _onUrlChanged(self):
        self.titleChanged.emit(self.title)
