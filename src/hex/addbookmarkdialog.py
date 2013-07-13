import math
from PyQt4.QtCore import Qt
from PyQt4.QtGui import QColor, QPixmap, QIcon, QColorDialog, QDialogButtonBox, QButtonGroup
import hex.utils as utils
import hex.hexwidget as hexwidget
from hex.forms.ui_addbookmarkdialog import Ui_AddBookmarkDialog
import hex.settings as settings
import hex.appsettings as appsettings


currentBookmarkIndex = 1


def colorsDistance(color1, color2):
    return math.sqrt(pow(color1.red() - color2.red(), 2) + pow(color1.green() - color2.green(), 2) +
                     pow(color1.blue() - color2.blue(), 2))


class AddBookmarkDialog(utils.Dialog):
    def __init__(self, parent, hex_widget):
        utils.Dialog.__init__(self, parent, name='add_bookmark_dialog')
        self.hexWidget = hex_widget
        self.ui = Ui_AddBookmarkDialog()
        self.ui.setupUi(self)
        self._canCreateBookmark = True
        self._isColorChoosen = False

        self._groupMark = QButtonGroup()
        self._groupMark.addButton(self.ui.btnMarkCaret)
        self._groupMark.addButton(self.ui.btnMarkSelection)
        if self.hexWidget.hasSelection:
            self.ui.btnMarkSelection.setChecked(True)
        else:
            self.ui.btnMarkCaret.setChecked(True)

        self._groupBind = QButtonGroup()
        self._groupBind.addButton(self.ui.btnBoundToPosition)
        self._groupBind.addButton(self.ui.btnBoundToData)
        self.ui.btnBoundToData.setChecked(True)

        self._bookmarkColor = QColor(Qt.red)

        self.ui.btnMarkCaret.toggled.connect(self._updateOk)
        self.ui.btnMarkSelection.toggled.connect(self._updateOk)
        self.ui.btnMarkCaret.toggled.connect(self._updateColor)
        self.ui.btnMarkSelection.toggled.connect(self._updateColor)

        self.ui.btnSelectColor.clicked.connect(self._selectBookmarkColor)

        self._updateOk()

        bookmark_name = ''
        if self._canCreateBookmark:
            bookmark_range = self.createBookmark()
            # find existing bookmarks that contain this one
            c_bookmarks = [b for b in self.hexWidget.bookmarks if b.contains(bookmark_range)]

            if c_bookmarks:
                c_bookmark = min(c_bookmarks, key=lambda x: x.size)
                bookmark_name = c_bookmark.name + '.'

        if bookmark_name:
            self.ui.txtName.setText(bookmark_name)
        else:
            bookmark_name = utils.tr('bookmark{0}').format(currentBookmarkIndex)
            self.ui.txtName.setText(bookmark_name)
            self.ui.txtName.selectAll()

        self._updateColor()

    def _updateColorButton(self):
        pixmap = QPixmap(32, 32)
        pixmap.fill(self._bookmarkColor)
        self.ui.btnSelectColor.setIcon(QIcon(pixmap))

    def _updateOk(self):
        if self.ui.btnMarkCaret.isChecked():
            caret_pos = self.hexWidget.caretPosition
            enabled = caret_pos >= 0
        else:
            enabled = self.hexWidget.hasSelection
        self.ui.buttonBox.button(QDialogButtonBox.Ok).setEnabled(enabled)
        self._canCreateBookmark = enabled

    def _updateColor(self):
        if self._canCreateBookmark and not self._isColorChoosen:
            bookmark_range = self.createBookmark()

            i_bookmarks = [b for b in self.hexWidget.bookmarks if b.intersectsWith(bookmark_range)]
            distance = settings.globalSettings()[appsettings.HexWidget_RandomColorDistance]
            used_colors = [b.backgroundColor for b in i_bookmarks] + [self.hexWidget.theme.backgroundColor,
                                                                      self.hexWidget.theme.textColor]
            for i in range(100):
                bookmark_color = utils.generateRandomColor()
                if all(colorsDistance(bookmark_color, color) >= distance for color in used_colors):
                    break
            else:
                # we have not found acceptable color... Let's just find color that is not equal to existing.
                while bookmark_color not in used_colors:
                    bookmark_color = utils.generateRandomColor()

            self._bookmarkColor = bookmark_color
        self._updateColorButton()

    def _selectBookmarkColor(self):
        color = QColorDialog.getColor(self._bookmarkColor, self, utils.tr('Select color for bookmark'))
        if color.isValid():
            self._bookmarkColor = color
            self._updateColorButton()

    def createBookmark(self):
        bookmark = None
        if self.ui.btnMarkCaret.isChecked():
            caret_pos = self.hexWidget.caretPosition
            if caret_pos >= 0:
                bookmark = hexwidget.BookmarkedRange(self.hexWidget, caret_pos, 1, hexwidget.DataRange.UnitBytes,
                                                     self._boundTo)
        elif self.hexWidget.selectionRanges:
            select_range = self.hexWidget.selectionRanges[0]
            if select_range:
                bookmark = hexwidget.BookmarkedRange(self.hexWidget, select_range.start, select_range.length,
                                                     select_range.unit, self._boundTo)

        if bookmark is not None:
            bookmark.name = self.ui.txtName.text()
            bookmark.backgroundColor = self._bookmarkColor

        return bookmark

    @property
    def _boundTo(self):
        return hexwidget.DataRange.BoundToPosition if self.ui.btnBoundToPosition.isChecked() else hexwidget.DataRange.BoundToData

    def accept(self):
        global currentBookmarkIndex
        currentBookmarkIndex += 1
        utils.Dialog.accept(self)

