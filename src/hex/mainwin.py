from PyQt4.QtCore import QFile, QFileInfo, Qt
from PyQt4.QtGui import QMainWindow, QMdiArea, QFileDialog, QKeySequence, QMdiSubWindow, QApplication, QProgressBar
from hex.hexwidget import HexWidget
import hex.settings as settings
import hex.appsettings as appsettings
import hex.utils as utils
import hex.files as files


class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self._inited = False

        self.setWindowTitle(QApplication.applicationName())

        self.mdiArea = QMdiArea()
        self.mdiArea.setViewMode(QMdiArea.TabbedView)
        self.mdiArea.setDocumentMode(True)
        self.mdiArea.setTabsClosable(True)
        self.mdiArea.setTabsMovable(True)
        self.mdiArea.subWindowActivated.connect(self._onSubWindowActivated)

        self.setCentralWidget(self.mdiArea)
        self.setFocusProxy(self.mdiArea)
        self.setFocus()

        menubar = self.menuBar()
        file_menu = menubar.addMenu(utils.tr('File'))
        action = file_menu.addAction(utils.tr('Open file...'))
        action.setShortcut(QKeySequence('Ctrl+O'))
        action.triggered.connect(self.openFileDialog)
        file_menu.addSeparator()
        file_menu.addAction(utils.tr('Close')).triggered.connect(self.mdiArea.closeActiveSubWindow)
        file_menu.addSeparator()
        file_menu.addAction(utils.tr('Exit')).triggered.connect(self.close)

        edit_menu = menubar.addMenu(utils.tr('Edit'))
        action = edit_menu.addAction(utils.tr('Undo'))
        action.setShortcut(QKeySequence('Ctrl+Z'))
        action.triggered.connect(self.undo)
        action = edit_menu.addAction(utils.tr('Redo'))
        action.setShortcut(QKeySequence('Ctrl+Y'))
        action.triggered.connect(self.redo)
        edit_menu.addSeparator()

        action = edit_menu.addAction(utils.tr('Copy'))
        action.setShortcut(QKeySequence('Ctrl+C'))
        action.triggered.connect(self.copy)
        action = edit_menu.addAction(utils.tr('Paste'))
        action.setShortcut(QKeySequence('Ctrl+V'))
        action.triggered.connect(self.paste)
        edit_menu.addSeparator()

        action = edit_menu.addAction(utils.tr('Clear selection'))
        action.triggered.connect(self.clearSelection)
        action = edit_menu.addAction(utils.tr('Select all'))
        action.setShortcut(QKeySequence('Ctrl+A'))
        action.triggered.connect(self.selectAll)

        self.setFocus()

    def showEvent(self, event):
        if not self._inited:
            self.openFile('/home/victor/Документы/utf-16.txt')
            self._inited = True

    def closeEvent(self, event):
        self.mdiArea.closeAllSubWindows()
        if self.mdiArea.activeSubWindow() is not None:
            event.ignore()

    def openFileDialog(self):
        from hex.loadfiledialog import LoadFileDialog

        filename = QFileDialog.getOpenFileName(self, utils.tr('Open file'), utils.lastFileDialogPath())
        if filename:
            utils.setLastFileDialogPath(filename)

            load_dialog = LoadFileDialog(self, filename)
            if load_dialog.exec_() == LoadFileDialog.Accepted:
                self.openFile(filename, load_dialog.loadOptions)

    def openFile(self, filename, load_options=None):
        self.mdiArea.addSubWindow(HexSubWindow(self, filename, files.editorFromFile(filename, load_options))).showMaximized()

    def _onSubWindowActivated(self, window):
        if window is not None and hasattr(window, 'path'):
            self.setWindowTitle('')
            self.setWindowFilePath(window.path)
        else:
            self.setWindowTitle(QApplication.applicationName())

    @property
    def activeHexWidget(self):
        subwin = self.mdiArea.activeSubWindow()
        if subwin is not None and hasattr(subwin, 'hexWidget'):
            return subwin.hexWidget
        return None

    def clearSelection(self):
        hw = self.activeHexWidget
        if hw is not None:
            hw.clearSelection()

    def selectAll(self):
        hw = self.activeHexWidget
        if hw is not None:
            hw.selectAll()

    def copy(self):
        hw = self.activeHexWidget
        if hw is not None:
            hw.copy()

    def paste(self):
        hw = self.activeHexWidget
        if hw is not None:
            hw.paste()

    def undo(self):
        hw = self.activeHexWidget
        if hw is not None:
            hw.undo()

    def redo(self):
        hw = self.activeHexWidget
        if hw is not None:
            hw.redo()


class HexSubWindow(QMdiSubWindow):
    def __init__(self, parent, filename, editor):
        QMdiSubWindow.__init__(self, parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.path = QFileInfo(filename).fileName()
        self.hexWidget = HexWidget(self, editor)
        self.setWidget(self.hexWidget)
        self.setFocusProxy(self.hexWidget)
        self.setWindowTitle(self.path)
