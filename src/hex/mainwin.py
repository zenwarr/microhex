from PyQt4.QtCore import QFileInfo, Qt, QByteArray, QObject, pyqtSignal, QUrl
from PyQt4.QtGui import QMainWindow, QTabWidget, QFileDialog, QKeySequence, QApplication, \
                        QWidget, QVBoxLayout, QFileIconProvider, QIcon, QDialog, QAction, QLabel, \
                        QMessageBox, QDockWidget, QColor
from hex.hexwidget import HexWidget, EmphasizeRange, Selection
import hex.settings as settings
import hex.utils as utils
import hex.documents as documents
import hex.operations as operations
import hex.search as search
import hex.inspector as inspector


def forActiveWidget(fn):
    def wrapped(self):
        if self.activeSubWidget is not None:
            return fn(self)
    return wrapped


globalSettings = settings.globalSettings()
globalQuickSettings = settings.globalQuickSettings()
globalMainWindow = None


class MainWindow(QMainWindow):
    activeSubWidgetChanged = pyqtSignal(object)

    def __init__(self, files_to_load):
        QMainWindow.__init__(self)
        self._inited = False
        self._currentMatcher = None
        self._lastMatch = None

        global globalMainWindow
        globalMainWindow = self

        self.setWindowTitle(QApplication.applicationName())
        self.setWindowIcon(QIcon(':/main/images/hex.png'))
        self.setMinimumSize(600, 400)

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

        self.dockSearch = SearchDockWidget(self)
        self.dockSearch.hide()
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dockSearch)

        self.dockInspector = InspectorDockWidget(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dockInspector)

        self.createActions()
        self.buildMenus()
        self.buildStatusbar()
        self.buildToolbar()

        geom = globalQuickSettings['mainWindow.geometry']
        if geom and isinstance(geom, str):
            self.restoreGeometry(QByteArray.fromHex(geom))
        else:
            self.resize(800, 600)

        state = globalQuickSettings['mainWindow.state']
        if state and isinstance(state, str):
            self.restoreState(QByteArray.fromHex(state))

        app = QApplication.instance()
        for file_to_load in files_to_load:
            load_options = documents.FileLoadOptions()
            load_options.readOnly = app.args.readOnly
            load_options.freezeSize = app.args.freezeSize
            if app.args.noLoadDialog:
                self.openFile(file_to_load, load_options)
            else:
                self.openFileWithOptionsDialog(file_to_load, load_options)

    def createActions(self):
        getIcon = utils.getIcon

        self.actionCreateDocument = QAction(getIcon('document-new'), utils.tr('Create...'), None)
        self.actionCreateDocument.setShortcut(QKeySequence('Ctrl+N'))
        self.actionCreateDocument.triggered.connect(self.newDocument)

        self.actionOpenFile = QAction(getIcon('document-open'), utils.tr('Open file...'), None)
        self.actionOpenFile.setShortcut(QKeySequence('Ctrl+O'))
        self.actionOpenFile.triggered.connect(self.openFileDialog)

        self.actionSave = ObservingAction(getIcon('document-save'), utils.tr('Save'),
                                          PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionSave.setShortcut(QKeySequence('Ctrl+S'))
        self.actionSave.triggered.connect(self.save)

        self.actionSaveAs = ObservingAction(getIcon('document-save-as'), utils.tr('Save as...'),
                                            PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionSaveAs.setShortcut(QKeySequence('Ctrl+Shift+S'))
        self.actionSaveAs.triggered.connect(self.saveAs)

        self.actionCloseTab = ObservingAction(getIcon('document-close'), utils.tr('Close'), PropertyObserver(self, 'activeSubWidget'))
        self.actionCloseTab.setShortcut(QKeySequence('Ctrl+W'))
        self.actionCloseTab.triggered.connect(self.closeActiveTab)
        
        self.actionExit = QAction(getIcon('application-exit'), utils.tr('Exit'), None)
        self.actionExit.triggered.connect(self.close)

        self.actionUndo = ObservingAction(getIcon('edit-undo'), utils.tr('Undo'),
                                          PropertyObserver(self, 'activeSubWidget.hexWidget.canUndo'))
        self.actionUndo.setShortcut(QKeySequence('Ctrl+Z'))
        self.actionUndo.triggered.connect(self.undo)

        self.actionRedo = ObservingAction(getIcon('edit-redo'), utils.tr('Redo'),
                                          PropertyObserver(self, 'activeSubWidget.hexWidget.canRedo'))
        self.actionRedo.setShortcut(QKeySequence('Ctrl+Y'))
        self.actionRedo.triggered.connect(self.redo)

        self.actionCopyAsData = ObservingAction(getIcon('edit-copy'), utils.tr('Copy as data'),
                                                PropertyObserver(self, 'activeSubWidget.hexWidget.hasSelection'))
        self.actionCopyAsData.setShortcut(QKeySequence('Ctrl+C'))
        self.actionCopyAsData.triggered.connect(self.copyAsData)

        self.actionCopyAsText = ObservingAction(QIcon(), utils.tr('Copy as text'),
                                                PropertyObserver(self, 'activeSubWidget.hexWidget.hasSelection'))
        self.actionCopyAsText.setShortcut(QKeySequence('Ctrl+Shift+C'))
        self.actionCopyAsText.triggered.connect(self.copyAsText)

        self.actionPaste = ObservingAction(getIcon('edit-paste'), utils.tr('Paste'),
                                           PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionPaste.setShortcut(QKeySequence('Ctrl+V'))
        self.actionPaste.triggered.connect(self.paste)

        self.actionClearSelection = ObservingAction(QIcon(), utils.tr('Clear selection'),
                                                    PropertyObserver(self, 'activeSubWidget.hexWidget.hasSelection'))
        self.actionClearSelection.setShortcut(QKeySequence('Ctrl+D'))
        self.actionClearSelection.triggered.connect(self.clearSelection)

        self.actionSelectAll = ObservingAction(getIcon('edit-select-all'), utils.tr('Select all'),
                                               PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionSelectAll.setShortcut(QKeySequence('Ctrl+A'))
        self.actionSelectAll.triggered.connect(self.selectAll)

        self.actionInsertMode = ObservingAction(QIcon(), utils.tr('Insert mode'),
                                                PropertyObserver(self, 'activeSubWidget.hexWidget'),
                                                PropertyObserver(self, 'activeSubWidget.hexWidget.insertMode'))
        self.actionInsertMode.triggered.connect(self.setInsertMode)

        self.actionRemoveSelected = ObservingAction(getIcon('edit-delete'), utils.tr('Remove selected'),
                                                    PropertyObserver(self, 'activeSubWidget.hexWidget.hasSelection'))
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

        self.actionShowSettings = QAction(getIcon('configure'), utils.tr('Settings...'), None)
        self.actionShowSettings.triggered.connect(self.showSettings)

        self.actionAbout = QAction(getIcon('help-about'), utils.tr('About program...'), None)
        self.actionAbout.triggered.connect(self.showAbout)

        self.actionZoomIn = ObservingAction(getIcon('zoom-in'), utils.tr('Increase font'),
                                            PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionZoomIn.triggered.connect(self.zoomIn)

        self.actionZoomOut = ObservingAction(getIcon('zoom-out'), utils.tr('Decrease font'),
                                             PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionZoomOut.triggered.connect(self.zoomOut)

        self.actionZoomReset = ObservingAction(getIcon('zoom-original'), utils.tr('Reset original font size'),
                                             PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionZoomReset.triggered.connect(self.zoomReset)

        self.actionGoto = ObservingAction(getIcon('go-jump'), utils.tr('Goto...'),
                                          PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionGoto.setShortcut(QKeySequence('Ctrl+G'))
        self.actionGoto.triggered.connect(self.goto)

        self.actionAddBookmark = ObservingAction(getIcon('bookmark-new'), utils.tr('Add bookmark...'),
                                                 PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionAddBookmark.triggered.connect(self.addBookmark)

        self.actionRemoveBookmark = ObservingAction(QIcon(), utils.tr('Remove bookmark'),
                                                    PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionRemoveBookmark.triggered.connect(self.removeBookmark)

        self.actionFind = ObservingAction(getIcon('edit-find'), utils.tr('Find...'),
                                            PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionFind.setShortcut(QKeySequence('Ctrl+F'))
        self.actionFind.triggered.connect(self.find)

        self.actionFindNext = ObservingAction(QIcon(), utils.tr('Find next'),
                                              PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionFindNext.setShortcut(QKeySequence('F3'))
        self.actionFindNext.triggered.connect(self.findNext)

        self.actionFindPrevious = ObservingAction(QIcon(), utils.tr('Find previous'),
                                                  PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionFindPrevious.setShortcut('Shift+F3')
        self.actionFindPrevious.triggered.connect(self.findPrevious)

        self.actionFindAll = ObservingAction(QIcon(), utils.tr('Find all...'),
                                             PropertyObserver(self, 'activeSubWidget.hexWidget'))
        self.actionFindAll.setShortcut('Ctrl+Shift+F')
        self.actionFindAll.triggered.connect(self.findAll)

        self.actionShowOperationManager = QAction(QIcon(), utils.tr('Show operation manager...'), None)
        self.actionShowOperationManager.triggered.connect(self.showOperationManager)

        # following actions for toggling dock windows will be updated by aboutToShow menu handler
        self.actionShowSearchPanel = ObservingAction(QIcon(), utils.tr('Search'),
                                                     checked_observer=PropertyObserver(self, 'dockSearch.isVisible'))
        self.actionShowSearchPanel.toggled.connect(self.dockSearch.setVisible)

        self.actionShowInspectorPanel = ObservingAction(QIcon(), utils.tr('Inspector'),
                                                        checked_observer=PropertyObserver(self, 'dockInspector.isVisible'))
        self.actionShowInspectorPanel.toggled.connect(self.dockInspector.setVisible)

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
        self.editMenu.addAction(self.actionCopyAsData)
        self.editMenu.addAction(self.actionCopyAsText)
        self.editMenu.addAction(self.actionPaste)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.actionClearSelection)
        self.editMenu.addAction(self.actionSelectAll)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.actionInsertMode)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.actionRemoveSelected)
        self.editMenu.addAction(self.actionFillZeros)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.actionGoto)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.actionAddBookmark)
        self.editMenu.addAction(self.actionRemoveBookmark)
        self.editMenu.addSeparator()
        self.editMenu.addAction(self.actionFind)
        self.editMenu.addAction(self.actionFindNext)
        self.editMenu.addAction(self.actionFindPrevious)
        self.editMenu.addAction(self.actionFindAll)

        self.viewMenu = menubar.addMenu(utils.tr('View'))
        self.viewMenu.addAction(self.actionShowHeader)
        self.viewMenu.addSeparator()
        self.viewMenu.addAction(self.actionZoomIn)
        self.viewMenu.addAction(self.actionZoomOut)
        self.viewMenu.addAction(self.actionZoomReset)
        self.viewMenu.addSeparator()
        self.viewMenu.addAction(self.actionSetupColumn)
        self.viewMenu.addAction(self.actionAddColumn)
        self.viewMenu.addAction(self.actionRemoveColumn)
        self.viewMenu.addAction(self.actionAddAddress)
        self.viewMenu.addSeparator()
        self.docksMenu = self.viewMenu.addMenu(utils.tr('Tool windows'))
        self.docksMenu.addAction(self.actionShowSearchPanel)
        self.docksMenu.addAction(self.actionShowInspectorPanel)
        self.docksMenu.aboutToShow.connect(self.actionShowSearchPanel.update)
        self.docksMenu.aboutToShow.connect(self.actionShowInspectorPanel.update)

        self.toolsMenu = menubar.addMenu(utils.tr('Tools'))
        self.toolsMenu.addAction(self.actionShowOperationManager)
        self.toolsMenu.addSeparator()
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

        self.operationsInfoWidget = OperationsStatusBarWidget(self)

        statusbar = self.statusBar()
        statusbar.addPermanentWidget(self.operationsInfoWidget)
        statusbar.addPermanentWidget(self.lblReadOnly)
        statusbar.addPermanentWidget(self.lblInsertMode)

    def buildToolbar(self):
        self.generalToolBar = self.addToolBar(utils.tr("General"))
        self.generalToolBar.setObjectName('toolbar_general')
        self.generalToolBar.addAction(self.actionCreateDocument)
        self.generalToolBar.addAction(self.actionOpenFile)
        self.generalToolBar.addAction(self.actionSave)

        self.editToolBar = self.addToolBar(utils.tr('Edit'))
        self.editToolBar.setObjectName('toolbar_edit')
        self.editToolBar.addAction(self.actionUndo)
        self.editToolBar.addAction(self.actionRedo)
        self.editToolBar.addAction(self.actionCopyAsData)
        self.editToolBar.addAction(self.actionPaste)
        self.editToolBar.addAction(self.actionFind)

    def showEvent(self, event):
        if not self._inited:
            self._inited = True

    def closeEvent(self, event):
        if not operations.onApplicationShutdown(self):
            event.ignore()
            return

        while self.tabsWidget.count():
            if not self.closeTab(0):
                event.ignore()
                return

        globalQuickSettings['mainWindow.geometry'] = str(self.saveGeometry().toHex(), encoding='ascii')
        globalQuickSettings['mainWindow.state'] = str(self.saveState().toHex(), encoding='ascii')

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
        subWidget.setParent(None)
        return True

    def openFileDialog(self):
        filename = QFileDialog.getOpenFileName(self, utils.tr('Open file'), utils.lastFileDialogPath())
        if filename:
            utils.setLastFileDialogPath(filename)
            self.openFileWithOptionsDialog(filename, None)

    def openFileWithOptionsDialog(self, filename, load_options=None):
        from hex.loadfiledialog import LoadFileDialog

        load_dialog = LoadFileDialog(self, filename, load_options)
        if load_dialog.exec_() == LoadFileDialog.Accepted:
            self.openFile(filename, load_dialog.loadOptions)

    def openFile(self, filename, load_options=None):
        try:
            e = documents.Document(documents.deviceFromUrl(QUrl.fromLocalFile(filename), load_options))
        except Exception as err:
            msgbox = QMessageBox(self)
            msgbox.setWindowTitle(utils.tr('Error opening file'))
            msgbox.setTextFormat(Qt.RichText)
            msgbox.setText(utils.tr('Failed to open file<br><b>{0}</b><br>due to following error:<br><b>{1}</b>')
                           .format(utils.htmlEscape(filename), utils.htmlEscape(str(err))))
            msgbox.addButton(QMessageBox.Ok)
            msgbox.exec_()
            return

        subWidget = HexSubWindow(self, e)
        self._addTab(subWidget)

    @forActiveWidget
    def saveAs(self):
        hex_widget = self.activeSubWidget.hexWidget
        if hex_widget.document.device is not None:
            url = hex_widget.document.device.url
            filename = url.toLocalFile() if url.isLocalFile() else ''
        else:
            filename = ''

        filename = QFileDialog.getSaveFileName(self, utils.tr('Save file as'), filename)
        if filename:
            options = documents.FileLoadOptions()
            options.forceNew = True
            save_device = documents.deviceFromUrl(QUrl.fromLocalFile(filename), options)
            hex_widget.save(save_device, switch_to_device=True)

    def newDocument(self):
        e = documents.Document()
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

        self.dockInspector.hexWidget = subWidget.hexWidget if subWidget is not None else None

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
    def copyAsData(self):
        self.activeSubWidget.hexWidget.copyAsData()

    @forActiveWidget
    def copyAsText(self):
        self.activeSubWidget.hexWidget.copyAsText()

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
        self.activeSubWidget.hexWidget.fillSelected('\x00')

    @forActiveWidget
    def setupActiveColumn(self):
        self.activeSubWidget.hexWidget.setupActiveColumn()

    @forActiveWidget
    def addColumn(self):
        import hex.columnproviders as columnproviders
        dlg = columnproviders.CreateColumnDialog(self, self.activeSubWidget.hexWidget)
        if dlg.exec_() == QDialog.Accepted:
            hexWidget = self.activeSubWidget.hexWidget
            hexWidget.insertColumn(dlg.createColumnModel(), hexWidget.columnIndex(hexWidget.leadingColumn) + 1)

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
        if not self.activeSubWidget.hexWidget.document.device:
            self.saveAs()
        else:
            self.activeSubWidget.hexWidget.save()

    @forActiveWidget
    def zoomIn(self):
        self.activeSubWidget.hexWidget.zoom(1)

    @forActiveWidget
    def zoomOut(self):
        self.activeSubWidget.hexWidget.zoom(-1)

    @forActiveWidget
    def zoomReset(self):
        self.activeSubWidget.hexWidget.zoomReset()

    @forActiveWidget
    def goto(self):
        from hex.gotodialog import GotoDialog

        dlg = GotoDialog(self, self.activeSubWidget.hexWidget)
        if dlg.exec_() == QDialog.Accepted:
            self.activeSubWidget.hexWidget.goto(dlg.address)

    @forActiveWidget
    def addBookmark(self):
        from hex.addbookmarkdialog import AddBookmarkDialog

        dlg = AddBookmarkDialog(self, self.activeSubWidget.hexWidget)
        if dlg.exec_() == QDialog.Accepted:
            bookmark = dlg.createBookmark()
            if bookmark is not None:
                self.activeSubWidget.hexWidget.addBookmark(bookmark)

    @forActiveWidget
    def removeBookmark(self):
        hexWidget = self.activeSubWidget.hexWidget
        bookmarks = hexWidget.bookmarksAtIndex(hexWidget.caretIndex(hexWidget.leadingColumn))
        if bookmarks:
            # select innermost (by name) bookmark and remove it
            bookmarks.sort(key=lambda x: x.innerLevel, reverse=True)
            hexWidget.removeBookmark(bookmarks[0])

    @forActiveWidget
    def findAll(self):
        dlg = search.SearchDialog(self, self.activeSubWidget.hexWidget)
        if dlg.exec_() == QDialog.Accepted:
            matcher = dlg.matcher
            self.dockSearch.newSearch(self.activeSubWidget.hexWidget, matcher)
            matcher.run()

    def _ensureCurrentMatcher(self):
        if utils.isNone(self._currentMatcher) or not utils.isClone(self._currentMatcher.document,
                                                                   self._activeSubWidget.hexWidget.document):
            dlg = search.SearchDialog(self, self.activeSubWidget.hexWidget)
            if dlg.exec_() == QDialog.Accepted:
                self._currentMatcher = dlg.matcher

    def _doFind(self, reverse):
        self._ensureCurrentMatcher()
        if not utils.isNone(self._currentMatcher):
            hex_widget = self._activeSubWidget.hexWidget
            if not reverse:
                match = self._currentMatcher.findNext(hex_widget.caretPosition + 1)
            else:
                match = self._currentMatcher.findPrevious(hex_widget.caretPosition)

            if not match.valid:
                QMessageBox.information(self, utils.tr('Find'), utils.tr('Nothing had been found'))
            else:
                emp_range = EmphasizeRange(QColor(Qt.green), utils.DocumentRange(hex_widget.document,
                                                                         match.position, match.length))
                hex_widget.emphasize(emp_range)
                hex_widget.caretPosition = match.position
                hex_widget.selections = [Selection(utils.DocumentRange(hex_widget.document,
                                                                       match.position, match.length,
                                                                       fixed=False, allow_resize=False))]
            self._lastMatch = match

    @forActiveWidget
    def find(self):
        dlg = search.SearchDialog(self, self.activeSubWidget.hexWidget)
        if dlg.exec_() == QDialog.Accepted:
            self._currentMatcher = dlg.matcher
            self.findNext()

    @forActiveWidget
    def findNext(self):
        self._doFind(reverse=False)

    @forActiveWidget
    def findPrevious(self):
        self._doFind(reverse=True)

    def showOperationManager(self):
        operations.OperationsDialog(self).exec_()


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
        self.update()

    def update(self):
        old_value = self.value
        self.value = None
        new_value = None
        for signal in self._connectedSignals:
            signal.disconnect(self.update)
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
                    signal.connect(self.update)
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
    def __init__(self, icon, text, enabled_observer=None, checked_observer=None):
        QAction.__init__(self, icon, text, None)
        self.enabledObserver = enabled_observer
        self.checkedObserver = checked_observer
        if enabled_observer is not None:
            enabled_observer.valueChanged.connect(lambda f: self.setEnabled(bool(f)))
            self.setEnabled(bool(enabled_observer.value))
        if checked_observer is not None:
            self.setCheckable(True)
            checked_observer.valueChanged.connect(lambda f: self.setChecked(bool(f)))
            self.setChecked(bool(checked_observer.value))

    def update(self):
        if self.enabledObserver is not None:
            self.enabledObserver.update()
        if self.checkedObserver is not None:
            self.checkedObserver.update()


class HexSubWindow(QWidget):
    titleChanged = pyqtSignal(str)
    isModifiedChanged = pyqtSignal(bool)

    def __init__(self, parent, document, name=''):
        QWidget.__init__(self, parent)
        if document.url.isLocalFile():
            self.icon = QFileIconProvider().icon(QFileInfo(document.url.toLocalFile()))
        else:
            self.icon = QIcon()
        self.name = name
        self.hexWidget = HexWidget(self, document)
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
            name = QFileInfo(self.hexWidget.url.toLocalFile()).fileName()
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


class OperationsStatusBarWidget(operations.OperationsInfoWidget):
    def __init__(self, parent=None):
        operations.OperationsInfoWidget.__init__(self, parent)

    def _setOperation(self, old_operation, new_operation):
        operations.OperationsInfoWidget._setOperation(self, old_operation, new_operation)
        self.setVisible(new_operation is not None)


class SearchDockWidget(QDockWidget):
    def __init__(self, parent):
        QDockWidget.__init__(self, utils.tr('Search'), parent)
        self.setObjectName('dock-search')

        self.searchResults = search.SearchResultsWidget(self)
        self.setWidget(self.searchResults)

    def newSearch(self, hex_widget, matchOperation):
        self.searchResults.hexWidget = hex_widget
        self.searchResults.matchOperation = matchOperation
        self.setVisible(True)


class InspectorDockWidget(QDockWidget):
    def __init__(self, parent):
        QDockWidget.__init__(self, utils.tr('Inspector'), parent)
        self.setObjectName('dock-inspector')

        self.inspector = inspector.InspectorWidget(self)
        self.inspector.inspectorView.doubleClicked.connect(lambda index: self._selectFromIndex(index))
        self.setWidget(self.inspector)

        self._addDefaultTypes()

        self._hexWidgetConnector = utils.SignalConnector(None, caretPositionChanged=self._updateCursor)

    @property
    def hexWidget(self):
        return self._hexWidgetConnector.target

    @hexWidget.setter
    def hexWidget(self, new_widget):
        self._hexWidgetConnector.target = new_widget
        self.setEnabled(new_widget is not None)
        self._updateCursor()

    def _addDefaultTypes(self):
        import hex.datatypes as datatypes

        for type_name in ('int8', 'uint8', 'int16', 'uint16', 'int32', 'uint32', 'int64', 'uint64', 'float'):
            self.inspector.inspectorModel.appendType(type_name)

        inst = datatypes.InstantiatedType(datatypes.globalTypeManager().getTemplate('zero_string'),
                                          datatypes.InstantiateContext(limit=1024))
        self.inspector.inspectorModel.appendType(inst)

        context = datatypes.InstantiateContext()
        context['fields'] = [
            datatypes.Structure.Field('a', datatypes.globalTypeManager().getTemplate('uint8')),
            datatypes.Structure.Field('b', datatypes.globalTypeManager().getTemplate('fixed_string'))
        ]
        context['links'] = [
            datatypes.Structure.Link('a', 'b.size')
        ]
        inst = datatypes.InstantiatedType(datatypes.globalTypeManager().getTemplate('struct'), context)
        self.inspector.inspectorModel.appendType(inst, 'struct_demo')

        context = datatypes.InstantiateContext()
        context['fields'] = [
            datatypes.Structure.Field('a_ign', datatypes.globalTypeManager().getTemplate('bool')),
            datatypes.Structure.Field('a1', datatypes.globalTypeManager().getTemplate('uint8')),
            datatypes.Structure.Field('a2', datatypes.globalTypeManager().getTemplate('uint8')),
            datatypes.Structure.Field('b_ign', datatypes.globalTypeManager().getTemplate('bool')),
            datatypes.Structure.Field('b', datatypes.globalTypeManager().getTemplate('uint8'))
        ]
        context['links'] = [
            datatypes.Structure.Link('a_ign', 'a1.ignore_field'),
            datatypes.Structure.Link('a_ign', 'a2.ignore_field'),
            datatypes.Structure.Link('b_ign', 'b.ignore_field')
        ]
        inst = datatypes.InstantiatedType(datatypes.globalTypeManager().getTemplate('struct'), context)
        self.inspector.inspectorModel.appendType(inst, 'dyn_struct')

    def _updateCursor(self):
        new_cursor = None
        if self._hexWidgetConnector.target is not None:
            hex_widget = self._hexWidgetConnector.target
            new_cursor = utils.DocumentCursor(hex_widget.document, hex_widget.caretPosition)
        self.inspector.inspectorModel.cursor = new_cursor

    def _selectFromIndex(self, index):
        if index.isValid() and self.hexWidget is not None:
            decoded = index.data(inspector.InspectorModel.ValueRole)
            if decoded is not None:
                self.hexWidget.endEditIndex(save=True)
                self.hexWidget.selections = [Selection(decoded.bufferRange)]
