from PyQt4.QtCore import pyqtSignal, QObject, Qt, QPointF, QRectF, QPoint, QSizeF, QEvent, QTimer, QLineF, QUrl, \
                        QEasingCurve, QSequentialAnimationGroup, pyqtProperty, QPropertyAnimation
from PyQt4.QtGui import QColor, QFont, QFontMetricsF, QPolygonF, QWidget, QScrollBar, QVBoxLayout, QHBoxLayout, \
                        QPainter, QBrush, QPalette, QPen, QApplication, QRegion, QLineEdit, QValidator, \
                        QTextEdit, QTextOption, QSizePolicy, QStyle, QStyleOptionFrameV2, QTextCursor, QTextDocument, \
                        QTextBlockFormat, QPlainTextDocumentLayout, QAbstractTextDocumentLayout, QTextCharFormat, \
                        QTextTableFormat, QRawFont, QKeyEvent, QFontDatabase, QMenu, QToolTip, QPixmap, QIcon, \
                        QMessageBox
import math
import html
import os
from hex.valuecodecs import IntegerCodec
from hex.formatters import IntegerFormatter
import hex.documents as documents
from hex.proxystyle import ProxyStyle
import hex.encodings as encodings
import hex.utils as utils
import hex.settings as settings
import hex.appsettings as appsettings
import hex.resources.qrc_main
import hex.formatters as formatters
from hex.models import ModelIndex, ColumnModel, FrameModel, StandardEditDelegate, index_range


class Theme(object):
    Components = ('background', 'text', 'border', 'inactiveText', 'caretBackground', 'caretBorder',
                  'selectionBackground', 'selectionBorder', 'cursorBackground', 'cursorBorder',
                  'modifiedText', 'brokenText', 'headerBackground', 'headerText', 'headerInactiveText',
                  'alternateRow')

    StandardAlpha = {
        'caretBackgroundColor': 100,
        'selectionBackgroundColor': 100,
        'cursorBackgroundColor': 100,
    }

    def __init__(self):
        self.name = ''
        self.backgroundColor = QColor(250, 250, 245)
        self.textColor = QColor(Qt.black)
        self.borderColor = QColor(Qt.black)
        self.inactiveTextColor = QColor(Qt.darkGray)
        self.caretBackgroundColor = QColor(150, 250, 160, 100)
        self.caretBorderColor = QColor(0, 0, 0, 255)
        self.selectionBackgroundColor = QColor(220, 250, 245, 100)
        self.selectionBorderColor = QColor(20, 205, 195)
        self.cursorBackgroundColor = QColor(100, 60, 60, 100)
        self.cursorBorderColor = QColor(Qt.black)
        self.modifiedTextColor = QColor(Qt.red)
        self.brokenTextColor = QColor(Qt.gray)
        self.headerBackgroundColor = self.backgroundColor
        self.headerTextColor = self.textColor
        self.headerInactiveTextColor = self.inactiveTextColor
        self.alternateRowColor = QColor(225, 225, 210)

    def load(self, s):
        s.load()
        for key in s.allSettings.keys():
            attr = utils.underscoreToCamelCase(key)
            if attr[:-5] in self.Components:
                stored_value = s[key]
                if isinstance(stored_value, str):
                    color = self.colorFromName(key, s[key])
                    if color.isValid():
                        setattr(self, attr, color)

    def save(self, name=None):
        if name is None:
            name = self.name
        if not name:
            return

        os.makedirs(Theme.themesDirectory(), exist_ok=True)
        s = settings.Settings(os.path.join(Theme.themesDirectory(), name + appsettings.ThemeExtension))

        for component in self.Components:
            color = getattr(self, component + 'Color')
            color_name = color.name()
            if color.alpha() != 255:
                color_name += ':' + str(color.alpha())
            s[utils.camelCaseToUnderscore(component + 'Color')] = color_name

        s.save()

    @staticmethod
    def colorFromName(component, name):
        if utils.underscoreToCamelCase(component) in Theme.StandardAlpha:
            alpha = Theme.StandardAlpha[utils.underscoreToCamelCase(component)]
        else:
            alpha = 255

        if ':' in name:
            # extract alpha-channel value
            colon_index = name.index(':')
            try:
                alpha = int(name[colon_index+1:])
            except ValueError:
                pass
            name = name[:colon_index]
        color = QColor()
        color.setNamedColor(name)
        color.setAlpha(alpha)
        return color

    @staticmethod
    def availableThemes():
        themes = list()
        themes_dir = Theme.themesDirectory()
        if os.path.exists(themes_dir):
            for filename in os.listdir(themes_dir):
                basename, ext = os.path.splitext(filename)
                if ext.lower() == appsettings.ThemeExtension:
                    themes.append(basename)
        return themes

    @staticmethod
    def themeFromName(theme_name):
        theme_file = os.path.join(Theme.themesDirectory(), theme_name + appsettings.ThemeExtension)
        if os.path.exists(theme_file):
            theme = Theme()
            theme.load(settings.Settings(theme_file))
            theme.name = theme_name
            return theme

    @staticmethod
    def themesDirectory():
        return os.path.join(settings.defaultSettingsDirectory, 'themes')


VisualSpace = 10


class RowData(object):
    def __init__(self):
        self.text = ''
        self.html = ''
        self.items = []


class IndexData(object):
    def __init__(self, index):
        self._text = None
        self.index = index
        self.firstCharIndex = 0
        self.firstHtmlCharIndex = 0
        self.html = None
        self.color = None
        self.delegate = None

    @property
    def text(self):
        return self.data()

    def data(self, role=Qt.DisplayRole):
        if self.delegate is not None:
            return self.delegate.data(role)
        if role == Qt.DisplayRole:
            if self._text is None:
                self._text = self.index.data()
            return self._text
        if self.index:
            return self.index.data(role)
        return None

    @property
    def flags(self):
        if self.delegate is not None:
            return self.delegate.flags
        else:
            return self.index.flags


class ColumnDocumentBackend(QObject):
    """Document backend controls generation of QTextDocument html structure and interacts with underlying QTextDocument.
    """

    documentUpdated = pyqtSignal()

    def __init__(self, column):
        QObject.__init__(self)
        self._document = None
        self._column = column

    @property
    def document(self):
        if self._document is None:
            self.generateDocument()
        return self._document

    @property
    def generated(self):
        return self._document is not None

    def generateDocument(self):
        raise NotImplementedError()

    def updateRow(self, row_index, cached_row):
        raise NotImplementedError()

    def removeRows(self, row_index, number_of_rows):
        raise NotImplementedError()

    def insertRow(self, row_index, number_of_rows):
        raise NotImplementedError()

    def rectForIndex(self, index):
        raise NotImplementedError()

    def cursorPositionInIndex(self, index, cursor_offset):
        raise NotImplementedError()

    def indexFromPoint(self, point):
        raise NotImplementedError()

    def cursorPositionFromPoint(self, point):
        raise NotImplementedError()

    def invalidate(self):
        self._document = None


class TextDocumentBackend(ColumnDocumentBackend):
    def __init__(self, column):
        ColumnDocumentBackend.__init__(self, column)

    def generateDocument(self):
        """Generates document if backend was invalidated."""
        if self._document is None:
            self._document = self._column.createDocumentTemplate()

            cursor = QTextCursor(self._document)
            cursor.beginEditBlock()
            try:
                block_format = self._documentBlockFormat
                for row_index in range(self._column.visibleRows):
                    row_data = self._column.getRowCachedData(row_index)
                    cursor.movePosition(QTextCursor.End)
                    cursor.insertHtml(row_data.html)
                    cursor.insertBlock()
                    cursor.setBlockFormat(block_format)
            finally:
                cursor.endEditBlock()

            self.documentUpdated.emit()
        else:
            self._column._renderDocumentData()

    @property
    def _documentBlockFormat(self):
        block_format = QTextBlockFormat()
        block_format.setLineHeight(self._column._fontMetrics.height(), QTextBlockFormat.FixedHeight)
        return block_format

    def updateRow(self, row_index, row_data):
        if self._document is not None:
            block = self._document.findBlockByLineNumber(row_index)
            if block.isValid():
                cursor = QTextCursor(block)
                cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
                cursor.insertHtml(row_data.html)

                self.documentUpdated.emit()

    def removeRows(self, row_index, number_of_rows):
        if self._document is not None:
            block = self._document.findBlockByLineNumber(row_index)
            if block.isValid():
                cursor = QTextCursor(block)
                cursor.beginEditBlock()
                try:
                    for x in range(number_of_rows):
                        cursor.movePosition(QTextCursor.NextBlock, QTextCursor.KeepAnchor)
                    cursor.removeSelectedText()
                finally:
                    cursor.endEditBlock()

            self.documentUpdated.emit()

    def insertRows(self, row_index, number_of_rows):
        if self._document is not None:
            if row_index < 0:
                cursor = QTextCursor(self._document)
                cursor.movePosition(QTextCursor.End)
            else:
                block = self._document.findBlockByLineNumber(row_index)
                cursor = QTextCursor(block)

            cursor.beginEditBlock()
            try:
                for x in range(number_of_rows):
                    cursor.insertBlock()
                    cursor.setBlockFormat(self._documentBlockFormat)
            finally:
                cursor.endEditBlock()

            self.documentUpdated.emit()

    def rectForIndex(self, index):
        index = self._column.frameModel.toFrameIndex(index)
        if not index:
            return QRectF()

        self.generateDocument()
        index_data = self._column.getIndexCachedData(index)
        if index_data is not None:
            block = self._document.findBlockByLineNumber(index.row)
            if block.isValid():
                block_rect = self._document.documentLayout().blockBoundingRect(block)
                line = block.layout().lineAt(0)
                x = line.cursorToX(index_data.firstCharIndex)[0]
                y = block_rect.y() + line.position().y()
                width = self._column._fontMetrics.width(index_data.text)
                return QRectF(x, y, width, self._column._fontMetrics.height())
        return QRectF()

    def rectForRow(self, row_index):
        if isinstance(row_index, ModelIndex):
            return self.rectForRow(self._column.frameModel.toFrameIndex(row_index).row)

        self.generateDocument()

        block = self._document.findBlockByLineNumber(row_index)
        if block.isValid():
            block_rect = self._document.documentLayout().blockBoundingRect(block)
            return block_rect

        return QRectF()

    def cursorPositionInIndex(self, index, cursor_offset):
        index = self._column.frameModel.toFrameIndex(index)
        if not index:
            return QPointF()

        index_data = self._column.getIndexCachedData(index)
        if cursor_offset < 0 or cursor_offset > len(index_data.text):
            return QPointF()

        block = self._document.findBlockByLineNumber(index.row)
        if not block.isValid():
            return QPointF()

        line = block.layout().lineAt(0)
        x = line.cursorToX(index_data.firstCharIndex + cursor_offset)[0]
        y = self._document.documentLayout().blockBoundingRect(block).y() + line.position().y()
        return QPointF(x, y)

    def _positionForPoint(self, point):
        self.generateDocument()

        char_position = self._document.documentLayout().hitTest(point, Qt.ExactHit)
        block = self._document.findBlock(char_position)
        if block.isValid():
            row_index = block.firstLineNumber()
            row_data = self._column._cache[row_index]
            line_char_index = char_position - block.position()
            for column in range(len(row_data.items)):
                index_data = row_data.items[column]
                if line_char_index < index_data.firstCharIndex + len(index_data.text):
                    return index_data.index, line_char_index - index_data.firstCharIndex
        return ModelIndex(), 0

    def indexFromPoint(self, point):
        return self._positionForPoint(point)[0]

    def cursorPositionFromPoint(self, point):
        return self._positionForPoint(point)[1]


class Column(QObject):
    updateRequested = pyqtSignal()
    resizeRequested = pyqtSignal(QSizeF)
    headerResized = pyqtSignal()

    def __init__(self, model):
        QObject.__init__(self)
        self.dataModel = model
        self.frameModel = FrameModel(model)
        self.frameModel.frameScrolled.connect(self._onFrameScrolled)
        self.frameModel.frameResized.connect(self._onFrameResized)
        self.frameModel.rowsUpdated.connect(self._onRowsUpdated)

        self._geom = QRectF()
        self._font = QFont()
        self._fontMetrics = QFontMetricsF(self._font)
        self._theme = Theme()

        self._fullVisibleRows = 0
        self._visibleRows = 0
        self._firstVisibleRow = 0

        self._showHeader = True
        self._headerHeight = 0
        self._headerData = []
        self.selectionProxy = None

        self._spaced = self.dataModel.preferSpaced
        self._cache = []
        self._documentDirty = False
        self._documentBackend = TextDocumentBackend(self)
        self._documentBackend.documentUpdated.connect(self._onDocumentUpdated)

        self._updateHeaderData()
        self.dataModel.headerDataChanged.connect(self._updateHeaderData)

    @property
    def geometry(self):
        return self._geom

    @geometry.setter
    def geometry(self, rect):
        self._geom = rect
        self._updateGeometry()

    @property
    def showHeader(self):
        return self._showHeader

    @showHeader.setter
    def showHeader(self, show):
        self._showHeader = show
        self._updateGeometry()

    def idealHeaderHeight(self):
        return self._fontMetrics.height() + VisualSpace / 2

    @property
    def headerHeight(self):
        return self.headerRect.height()

    @headerHeight.setter
    def headerHeight(self, height):
        if self._headerHeight != height:
            self._headerHeight = height
            self.headerResized.emit()
            self._updateGeometry()

    @property
    def headerRect(self):
        if self.showHeader:
            return QRectF(QPointF(0, 0), QSizeF(self.geometry.width(), self._headerHeight))
        else:
            return QRectF()

    def rectForHeaderItem(self, section_index):
        cell_rect = self.rectForIndex(self.frameModel.index(0, section_index))
        return QRectF(QPointF(cell_rect.x(), 0), QSizeF(cell_rect.width(), self.headerRect.height()))

    @property
    def firstVisibleRow(self):
        return self._firstVisibleRow

    def scrollToFirstRow(self, source_row_index):
        if self._firstVisibleRow != source_row_index:
            self._firstVisibleRow = source_row_index
            self.frameModel.scrollFrame(self._firstVisibleRow)

    @property
    def lastFullVisibleRow(self):
        if self._fullVisibleRows > 0:
            return self._firstVisibleRow + self._fullVisibleRows - 1
        return self._firstVisibleRow

    @property
    def lastVisibleRow(self):
        if self._visibleRows > 0:
            return self._firstVisibleRow + self._visibleRows - 1
        return self._firstVisibleRow

    @property
    def visibleRows(self):
        return self._visibleRows

    @property
    def fullVisibleRows(self):
        return self._fullVisibleRows

    @property
    def firstVisibleIndex(self):
        return self.frameModel.index(0, 0)

    @property
    def lastVisibleIndex(self):
        return self.frameModel.lastIndex

    @property
    def lastFullVisibleIndex(self):
        return self.frameModel.lastRowIndex(self._fullVisibleRows - 1)

    @property
    def font(self):
        return self._font

    @font.setter
    def font(self, new_font):
        self._font = new_font
        self._fontMetrics = QFontMetricsF(new_font)
        if hasattr(self.dataModel, 'renderFont'):  # well, this is hack until i invent better solution...
            self.dataModel.renderFont = new_font
        self._documentBackend.invalidate()
        self.headerResized.emit()  # this can adjust geometry again...
        self._updateGeometry()

    @property
    def document(self):
        return self.dataModel.document

    @property
    def spaced(self):
        return self._spaced

    @spaced.setter
    def spaced(self, new_spaced):
        if self._spaced != new_spaced:
            self._spaced = new_spaced
            self._invalidateCache()

    @property
    def regular(self):
        return self.dataModel.regular

    def getRowCachedData(self, visible_row_index):
        if 0 <= visible_row_index < self._visibleRows:
            if self._cache[visible_row_index] is None:
                self._updateCachedRow(visible_row_index)
            return self._cache[visible_row_index]

    def getIndexCachedData(self, index):
        index = self.frameModel.toFrameIndex(index)
        row_data = self.getRowCachedData(index.row)
        if row_data is not None and index.column < len(row_data.items):
            return row_data.items[index.column]

    def rectForIndex(self, index):
        return self._documentBackend.rectForIndex(index).translated(self.documentOrigin)

    def cursorPositionInIndex(self, index, cursor_offset):
        return _translate(self._documentBackend.cursorPositionInIndex(index, cursor_offset), self.documentOrigin)

    def _alignRectangles(self, rects):
        if len(rects) < 2:
            return

        for j in range(1, len(rects)):
            space = rects[j].top() - rects[j - 1].bottom()
            rects[j - 1].moveBottom(rects[j - 1].bottom() + space / 2)
            rects[j].moveTop(rects[j].top() - space / 2)

    def polygonsForRange(self, first_index, last_index, join_lines):
        """Return tuple of polygons covering range of indexes from first_index until last_index (last_index is also
        included)."""

        first_index = self.frameModel.toSourceIndex(first_index)
        last_index = self.frameModel.toSourceIndex(last_index)

        if not first_index or not last_index:
            return tuple()

        first_visible_source_index = self.frameModel.toSourceIndex(self.firstVisibleIndex)
        last_visible_source_index = self.frameModel.toSourceIndex(self.lastVisibleIndex)
        if first_index > last_visible_source_index or last_index < first_visible_source_index:
            return tuple()

        # collapse range to frame boundaries
        first_index = max(first_index, first_visible_source_index)
        last_index = min(last_index, last_visible_source_index)

        if first_index == last_index:
            return QPolygonF(self.rectForIndex(first_index)),
        else:
            r1 = self.rectForIndex(first_index)
            row1_rect = self.rectForRow(first_index)
            rect1 = QRectF(QPointF(r1.left(), row1_rect.top()), row1_rect.bottomRight())

            r2 = self.rectForIndex(last_index)
            row2_rect = self.rectForRow(last_index)
            rect2 = QRectF(row2_rect.topLeft(), QPointF(r2.right(), row2_rect.bottom()))

            if first_index.row == last_index.row:
                return QPolygonF(QRectF(QPointF(r1.left(), row1_rect.top()), QPointF(r2.right(), row2_rect.bottom()))),
            elif first_index.row + 1 == last_index.row and r1.left() > r2.right():
                if join_lines:
                    self._alignRectangles((rect1, rect2))
                return QPolygonF(rect1), QPolygonF(rect2)
            else:
                rects = []
                for row_index in range(first_index.row + 1, last_index.row):
                    rects.append(self.rectForRow(row_index - self._firstVisibleRow))

                rects = [rect1] + rects + [rect2]
                if join_lines:
                    self._alignRectangles(rects)

                    polygon = QPolygonF()
                    for rect in rects:
                        polygon.append(rect.topLeft())
                        polygon.append(rect.bottomLeft())

                    for rect in reversed(rects):
                        polygon.append(rect.bottomRight())
                        polygon.append(rect.topRight())

                    return polygon,
                else:
                    return [QPolygonF(rect) for rect in rects]

    def indexFromPoint(self, point):
        point = _translate(point, -self.documentOrigin.x(), -self.documentOrigin.y())
        return self.frameModel.toSourceIndex(self._documentBackend.indexFromPoint(point))

    def cursorPositionFromPoint(self, point):
        point = _translate(point, -self.documentOrigin.x(), -self.documentOrigin.y())
        return self._documentBackend.cursorPositionFromPoint(point)

    def paint(self, paint_data):
        painter = paint_data.painter
        painter.save()

        painter.setPen(self._theme.textColor if paint_data.leadingColumn is self else self._theme.inactiveTextColor)

        if settings.globalSettings()[appsettings.HexWidget_AlternatingRows]:
            for row_index in range(self._visibleRows):
                if (row_index + self._firstVisibleRow) % 2:
                    rect = self.rectForRow(row_index)
                    rect = QRectF(QPointF(0, rect.y()), QSizeF(self.geometry.width(), rect.height()))
                    painter.fillRect(rect, QBrush(self._theme.alternateRowColor))

        painter.translate(self.documentOrigin)

        # little trick to quickly change default text color for document without re-generating it
        paint_context = QAbstractTextDocumentLayout.PaintContext()
        paint_context.palette.setColor(QPalette.Text, self._theme.textColor if paint_data.leadingColumn is self
                                                      else self._theme.inactiveTextColor)
        paint_context.palette.setColor(QPalette.Window, QColor(0, 0, 0, 0))
        # standard QTextDocument.draw also sets clip rect here, but we already have one
        self._renderDocumentData()
        self._documentBackend.document.documentLayout().draw(painter, paint_context)

        painter.restore()

        self.paintHeader(paint_data)

    def paintCaret(self, paint_data, caret_position, edit_mode):
        painter = paint_data.painter
        if caret_position >= 0:
            caret_index = self.dataModel.indexFromPosition(caret_position)
            if caret_index and self.isIndexVisible(caret_index, False):
                caret_rect = self.rectForIndex(caret_index)
                if edit_mode:
                    caret_rect.adjust(-3, -3, 3, 3)
                painter.setBrush(QBrush(self._theme.caretBackgroundColor if not edit_mode else QColor(0, 0, 0, 0)))
                painter.setPen(self._theme.caretBorderColor)
                painter.drawRect(caret_rect)

    def paintSelection(self, paint_data, selection):
        if selection:
            painter = paint_data.painter
            painter.setBrush(self._theme.selectionBackgroundColor)
            painter.setPen(QPen(QBrush(self._theme.selectionBorderColor), 2.0))
            for sel_polygon in self.polygonsForRange(self.dataModel.indexFromPosition(selection.startPosition),
                                        self.dataModel.indexFromPosition(selection.startPosition + selection.size - 1),
                                        join_lines=True):
                painter.drawPolygon(sel_polygon)

    def paintHighlight(self, paint_data, hl_range, ignore_alpha):
        if hl_range and hl_range.backgroundColor is not None:
            painter = paint_data.painter
            back_color = hl_range.backgroundColor
            if ignore_alpha:
                back_color.setAlpha(settings.globalSettings()[appsettings.HexWidget_HighlightAlpha])
            painter.setBrush(back_color)
            painter.setPen(QPen(back_color))
            for polygon in self.polygonsForRange(self.dataModel.indexFromPosition(hl_range.startPosition),
                                                 self.dataModel.indexFromPosition(hl_range.startPosition + hl_range.size - 1),
                                                 join_lines=False):
                painter.drawPolygon(polygon)

    class HeaderItemData(object):
        def __init__(self):
            self.text = ''

    def _updateHeaderData(self):
        self._headerData = []

        for column_index in range(self.dataModel.columnCount(0)):
            cell_data = self.dataModel.headerData(column_index, Qt.DisplayRole)
            if not isinstance(cell_data, str):
                cell_data = ''
            header_item_data = self.HeaderItemData()
            header_item_data.text = cell_data
            self._headerData.append(header_item_data)

    def paintHeader(self, paint_data):
        # header can be painted only for regular columns
        if not self.showHeader:
            return

        painter = paint_data.painter
        painter.setPen(self._theme.headerTextColor if paint_data.leadingColumn is self else self._theme.headerInactiveTextColor)

        painter.fillRect(self.headerRect, self._theme.headerBackgroundColor)

        for section_index in range(len(self._headerData)):
            rect = self.rectForHeaderItem(section_index)
            painter.drawText(rect, Qt.AlignHCenter | Qt.TextSingleLine, self._headerData[section_index].text)

    @property
    def documentOrigin(self):
        return QPointF(VisualSpace, self.headerRect.height() + VisualSpace / 2)

    def _updateGeometry(self):
        """Should be called every time column geometry (size, font, header height) was changed. Recalculates
        number of visible rows and adjusts frame size"""

        real_height = max(self._geom.height() - self.documentOrigin.y(), 0)
        self._fullVisibleRows = int(real_height // self._fontMetrics.height())
        self._visibleRows = self._fullVisibleRows + bool(int(real_height) % int(self._fontMetrics.height()))
        self.frameModel.resizeFrame(self._visibleRows)
        self.updateRequested.emit()  # we cannot rely on resizeFrame to initiate column update: frame size can
                                     # remain the same (for small resizes) but column still needs to be repainted.

    def _invalidateCache(self):
        self._cache = [None] * self._visibleRows
        self._documentDirty = True

    def _renderDocumentData(self):
        """Document will contain actual data after calling this method"""
        if self._documentDirty:
            for row_index in range(len(self._cache)):
                # update only invalidated rows
                if self._cache[row_index] is None:
                    self._updateCachedRow(row_index)
                    self._documentBackend.updateRow(row_index, self._cache[row_index])
            self._documentDirty = False

    def _onDocumentUpdated(self):
        ideal_width = self._documentBackend._document.idealWidth() + VisualSpace * 2
        if ideal_width != self._geom.width():
            self.resizeRequested.emit(QSizeF(ideal_width, self._geom.height()))

    def _updateCachedRow(self, row_index):
        row_data = RowData()
        row_data.html = '<div class="row">'
        column_count = self.frameModel.columnCount(row_index)
        for column_index in range(column_count):
            index = self.frameModel.toSourceIndex(self.frameModel.index(row_index, column_index))
            index_data = IndexData(index)
            if self.frameModel.activeDelegate is not None and self.frameModel.activeDelegate.index == index:
                index_data.delegate = self.frameModel.activeDelegate
            index_data.firstCharIndex = len(row_data.text)
            index_data.firstHtmlCharIndex = len(row_data.html)
            index_text = index_data.text

            if index_text is not None:
                cell_classes = []

                flags = index_data.flags
                if flags & ColumnModel.FlagModified:
                    cell_classes.append('cell-mod')
                if flags & ColumnModel.FlagBroken:
                    cell_classes.append('cell-broken')

                prepared_text = utils.htmlEscape(index_text)
                if cell_classes:
                    # unfortunately, HTML subset supported by Qt does not include multiclasses
                    for css_class in cell_classes:
                        index_html = '<span class="{0}">{1}</span>'.format(css_class, prepared_text)
                else:
                    index_html = prepared_text

                row_data.html += index_html
                row_data.text += index_text
                index_data.html = index_html

            if self.spaced and column_index + 1 < column_count:
                row_data.text += ' '
                row_data.html += '&nbsp;'

            row_data.items.append(index_data)

        row_data.html += '</div>'
        self._cache[row_index] = row_data

    def _onFrameScrolled(self, new_first_row, old_first_row):
        # do we have any rows that can be kept in cache?
        if new_first_row > old_first_row and new_first_row < old_first_row + len(self._cache):
            # frame is scrolled down, we can copy some rows from bottom to top
            scrolled_by = new_first_row - old_first_row
            valid_rows = len(self._cache) - scrolled_by
            self._cache[:valid_rows] = self._cache[-valid_rows:]

            if self._documentBackend.generated:
                # remove first scrolled_by rows from document
                self._documentBackend.removeRows(0, scrolled_by)
                self._documentBackend.insertRows(-1, scrolled_by)

            self._cache[valid_rows:valid_rows+scrolled_by] = [None] * scrolled_by
            self._documentDirty = True
        elif new_first_row < old_first_row and new_first_row + len(self._cache) > old_first_row:
            # frame is scrolled up, we can copy some rows from top to bottom
            scrolled_by = old_first_row - new_first_row
            valid_rows = len(self._cache) - scrolled_by
            self._cache[-valid_rows:] = self._cache[:valid_rows]

            if self._documentBackend.generated is not None:
                # remove last scrolled_by rows from document
                self._documentBackend.removeRows(valid_rows, scrolled_by)
                # and insert some rows into beginning
                self._documentBackend.insertRows(0, scrolled_by)

            self._cache[0:scrolled_by] = [None] * scrolled_by
            self._documentDirty = True
        else:
            # unfortunately... we should totally reset cache
            self._cache = [None] * self._visibleRows
            self._documentBackend.invalidate()

        self.updateRequested.emit()

    def _onFrameResized(self, new_frame_size, old_frame_size):
        if len(self._cache) > new_frame_size:
            self._cache = self._cache[:new_frame_size]
        elif len(self._cache) < new_frame_size:
            self._cache += [None] * (new_frame_size - len(self._cache))

        if self._documentBackend.generated:
            if new_frame_size < old_frame_size:
                # just remove some rows...
                self._documentBackend.removeRows(new_frame_size, old_frame_size - new_frame_size)
            else:
                # add new rows and initialize them
                self._documentBackend.insertRows(-1, new_frame_size - old_frame_size)
            self._documentDirty = True

        self.updateRequested.emit()

    def _onRowsUpdated(self, first_row, row_count):
        self._cache[first_row:first_row + row_count] = [None] * row_count
        self._documentDirty = True
        self.updateRequested.emit()

    def isIndexVisible(self, index, full_visible=False):
        index = self.frameModel.toFrameIndex(index)
        return (bool(index) and index.row < self._fullVisibleRows) if full_visible else bool(index)

    def isRangeVisible(self, data_range):
        if not data_range:
            return False

        f = self.dataModel.indexFromPosition(data_range.startPosition)
        first_visible = self.frameModel.toSourceIndex(self.frameModel.firstIndex)
        if not f or not first_visible or f < first_visible:
            return False

        l = self.dataModel.indexFromPosition(data_range.startPosition + data_range.size)
        last_visible = self.frameModel.toSourceIndex(self.frameModel.lastIndex)
        if not l or not last_visible or l > last_visible:
            return False

        return True

    def createDocumentTemplate(self):
        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setDefaultFont(self.font)
        document.setUndoRedoEnabled(False)

        document.setDefaultStyleSheet("""
            .cell-mod {{
                color: {mod_color};
            }}

            .cell-broken {{
                color: {broken_color};
            }}
        """.format(mod_color=self._theme.modifiedTextColor.name(), broken_color=self._theme.brokenTextColor.name()))

        return document

    @property
    def validator(self):
        return self.dataModel.createValidator()

    def rectForRow(self, row_index):
        return self._documentBackend.rectForRow(row_index).translated(self.documentOrigin)

    def translateIndex(self, index):
        return self.dataModel.indexFromPosition(index.data(ColumnModel.DocumentPositionRole))


def _translate(x, dx, dy=0):
    if isinstance(dx, (QPoint, QPointF)):
        return _translate(x, dx.x(), dx.y())

    if hasattr(x, 'translated'):
        return x.translated(QPointF(dx, dy))
    elif isinstance(x, (QPoint, QPointF)):
        return x + type(x)(dx, dy)
    else:
        raise TypeError('{0} is not translatable'.format(type(x)))


class HexWidget(QWidget):
    """HexWidget displays data in set of columns. One of columns is leading (just like widget can be focused).
    """

    insertModeChanged = pyqtSignal(bool)
    canUndoChanged = pyqtSignal(bool)
    canRedoChanged = pyqtSignal(bool)
    isModifiedChanged = pyqtSignal(bool)
    hasSelectionChanged = pyqtSignal(bool)
    leadingColumnChanged = pyqtSignal(object)
    showHeaderChanged = pyqtSignal(bool)
    urlChanged = pyqtSignal(QUrl)

    MethodShowBottom, MethodShowTop, MethodShowCenter = range(3)

    def __init__(self, parent, document):
        from hex.bigintscrollbar import BigIntScrollBar

        QWidget.__init__(self, parent)

        globalSettings = settings.globalSettings()

        self.view = QWidget(self)
        self.view.installEventFilter(self)
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusProxy(self.view)

        self.vScrollBar = BigIntScrollBar(Qt.Vertical, self)
        self.vScrollBar.valueChanged.connect(self._onVScroll)

        self.hScrollBar = QScrollBar(Qt.Horizontal, self)
        self.hScrollBar.valueChanged.connect(self._onHScroll)

        self.m_layout = QHBoxLayout(self)
        self.m_slayout = QVBoxLayout()
        self.m_slayout.addWidget(self.view)
        self.m_slayout.setContentsMargins(0, 0, 0, 0)
        self.m_slayout.addWidget(self.hScrollBar)
        self.m_layout.addLayout(self.m_slayout)
        self.m_layout.addWidget(self.vScrollBar)
        self.m_layout.setContentsMargins(0, 0, 0, 0)

        self._theme = Theme()
        self._document = document
        self._columns = []
        self._leadingColumn = None
        self._caretPosition = 0
        self._selections = []
        self._selectStartColumn = None
        self._selectStartIndex = None
        self._scrollTimer = None
        self._hasSelection = False
        self._bookmarks = []
        self._emphasizeRange = None
        self._draggingColumn = None
        self._columnInsertIndex = -1
        self._columnInsertIcon = utils.getIcon('arrow-up')

        self._activeDelegate = None
        self._cursorVisible = False
        self._cursorTimer = None
        self._blockCursor = globalSettings[appsettings.HexWidget_BlockCursor]
        self._insertMode = False

        self._showHeader = globalSettings[appsettings.HexWidget_ShowHeader]
        self._dx = 0

        self._contextMenu = QMenu()
        self._actionCopy = self._contextMenu.addAction(utils.tr('Copy'))
        # self._actionCopy.triggered.connect(self.copy)
        self._actionPaste = self._contextMenu.addAction(utils.tr('Paste'))
        # self._actionPaste.triggered.connect(self.paste)
        self._contextMenu.addSeparator()
        self._actionSetup = self._contextMenu.addAction(utils.tr('Setup column...'))
        self._actionSetup.triggered.connect(self.setupActiveColumn)

        self.setTheme(Theme.themeFromName(globalSettings[appsettings.HexWidget_Theme]) or Theme())
        self.view.setAutoFillBackground(True)

        self.setFont(appsettings.getFontFromSetting(globalSettings[appsettings.HexWidget_Font]))

        from hex.hexcolumn import HexColumnModel
        from hex.charcolumn import CharColumnModel
        from hex.addresscolumn import AddressColumnModel

        hex_column = HexColumnModel(self.document, IntegerCodec(IntegerCodec.Format8Bit, False),
                                    IntegerFormatter(16, padding=2))
        address_bar = AddressColumnModel(hex_column)
        self.appendColumn(hex_column)
        self.insertColumn(address_bar, 0)

        self.appendColumn(CharColumnModel(self.document, encodings.getCodec('ISO-8859-1'), self.font()))
        self.appendColumn(CharColumnModel(self.document, encodings.getCodec('UTF-16le'), self.font()))
        self.leadingColumn = self._columns[1]

        conn_mode = Qt.DirectConnection if utils.testRun else Qt.QueuedConnection
        self.document.canUndoChanged.connect(self.canUndoChanged, conn_mode)
        self.document.canRedoChanged.connect(self.canRedoChanged, conn_mode)
        self.document.isModifiedChanged.connect(self.isModifiedChanged, conn_mode)
        self.document.urlChanged.connect(self.urlChanged, conn_mode)

        globalSettings.settingChanged.connect(self._onSettingChanged)

    def saveSettings(self, settings):
        settings[appsettings.HexWidget_ShowHeader] = self.showHeader

    def _onSettingChanged(self, name, value):
        if name == appsettings.HexWidget_ShowHeader:
            self.showHeader = value
        elif name == appsettings.HexWidget_AlternatingRows:
            self.view.update()
        elif name == appsettings.HexWidget_Font:
            self.setFont(appsettings.getFontFromSetting(value))
        elif name == appsettings.HexWidget_Theme:
            self.setTheme(value)

    def setTheme(self, theme):
        if isinstance(theme, str):
            theme = Theme.themeFromName(theme) or Theme()

        self._theme = theme
        palette = QPalette(self.view.palette())
        palette.setColor(QPalette.Background, self._theme.backgroundColor)
        self.view.setPalette(palette)
        for column in self._columns:
            column._theme = self._theme
        self.view.update()

    @property
    def document(self):
        return self._document

    def setFont(self, new_font):
        QWidget.setFont(self, new_font)
        for column in self._columns:
            column.font = self.font()
        self._updateScrollBars()

    @property
    def editMode(self):
        return self._activeDelegate is not None

    @property
    def leadingColumn(self):
        return self._leadingColumn

    @leadingColumn.setter
    def leadingColumn(self, new_column):
        if new_column is not self._leadingColumn:
            self._leadingColumn = new_column
            self.leadingColumnChanged.emit(self._leadingColumn)
            self.view.update()

    @property
    def caretPosition(self):
        return self._caretPosition

    @caretPosition.setter
    def caretPosition(self, new_pos):
        """If widget is in edit mode and caret index in leading column is changed, changes are saved.
        """
        if self.caretPosition != new_pos and self.caretPosition <= utils.MaximalPosition:
            # if we are in edit mode, we should end editing of index if caret index was changed. Note that
            # caret index in column being edited can stay the same even if caret position was changed.

            if self.editMode:
                old_caret_index = self.caretIndex(self._leadingColumn)
            self._caretPosition = new_pos
            if self.editMode:
                new_caret_index = self.caretIndex(self._leadingColumn)
                if new_caret_index != old_caret_index:
                    self.endEditIndex(save=True)
                    self.beginEditIndex(new_caret_index)
            self.view.update()

    def caretIndex(self, column=None):
        if column is None:
            column = self._leadingColumn
        return column.dataModel.indexFromPosition(self.caretPosition) if column is not None else ModelIndex()

    def insertColumn(self, model, at_index=-1):
        if model is not None:
            column = Column(model)
            column.font = self.font()
            column._theme = self._theme

            column.geometry = QRectF(QPointF(0, 0), QSizeF(200, self.view.height()))
            column.showHeader = self.showHeader
            self._columns.insert(at_index if at_index >= 0 else len(self._columns), column)

            self._adjustHeaderHeights()
            self._updateColumnsGeometry()

            column.updateRequested.connect(self._onColumnUpdateRequested)
            column.resizeRequested.connect(self._onColumnResizeRequested)
            column.headerResized.connect(self._adjustHeaderHeights)

            if self._leadingColumn is None:
                self._leadingColumn = column
            else:
                self.syncColumnsFrames(self.caretIndex(self._leadingColumn).row)

            if hasattr(model, 'linkedModel'):
                column.selectionProxy = self.columnFromModel(model.linkedModel)

            self.view.update()

    def appendColumn(self, model):
        self.insertColumn(model)

    def clearColumns(self):
        self._columns = []
        self._leadingColumn = None
        self._updateColumnsGeometry()
        self.view.update()

    def moveColumn(self, column, index):
        column_index = self.columnIndex(column)
        if column_index >= 0 and index != column_index:
            self._columns.insert(index, column)
            if column_index > index:
                del self._columns[column_index + 1]
            else:
                del self._columns[column_index]
            self._updateColumnsGeometry()

    def columnFromIndex(self, index):
        return self.columnFromModel(index.model)

    def columnFromModel(self, model):
        return utils.first(cd for cd in self._columns if cd.frameModel is model or cd.dataModel is model)

    def _columnToAbsolute(self, column, d):
        """There is several coordinate systems used in widget:
            - widget coordinates - coordinates that are relative to widget and limited to its size. These values
                                   are used by Qt;
            - absolute coordinates - logical coordinates that are relative to widget content (i.e. does not depend
                                   on widget horizontal scroll);
            - column coordinates - relative to column content - absolute coordinates translated to column.
        """
        if column is None:
            raise ValueError()
        return _translate(d, column.geometry.left())

    def _absoluteToColumn(self, column, d):
        if column is None:
            raise ValueError()
        return _translate(d, -column.geometry.left())

    def _absoluteToWidget(self, d):
        return _translate(d, -self._dx)

    def _widgetToAbsolute(self, d):
        return _translate(d, self._dx)

    class PaintData(object):
        pass

    def _paint(self, event):
        pd = self.PaintData()
        pd.painter = QPainter(self.view)
        pd.dirtyRect = event.rect()
        pd.dirtyRegion = event.region()
        pd.leadingColumn = self._leadingColumn

        for column in self._columns:
            self._paintColumn(pd, column)

        self._paintCursor(pd)
        self._paintBorders(pd)

        # draw arrow near the header when user is dragging column
        if self._columnInsertIndex >= 0:
            # find position for icon
            if self._columnInsertIndex < len(self._columns):
                border_pos = self._columns[self._columnInsertIndex].geometry.left()
            else:
                border_pos = self._columns[-1].geometry.right()
            border_pos -= 8

            self._columnInsertIcon.paint(pd.painter, border_pos, self.headerHeight, 16, 16)

    def _paintColumn(self, pd, column):
        painter = pd.painter

        painter.setClipRect(self._absoluteToWidget(column.geometry))
        painter.translate(self._absoluteToWidget(column.geometry.topLeft()))

        for bookmark in self._bookmarks:
            column.paintHighlight(pd, bookmark, True)

        if self._leadingColumn is column and self._emphasizeRange is not None:
            column.paintHighlight(pd, self._emphasizeRange, False)

        column.paint(pd)

        column.paintCaret(pd, self._caretPosition, (self.editMode and self._leadingColumn is column))

        # paint selections
        if not self.editMode or self._leadingColumn is not column:
            for sel in self._selections:
                column.paintSelection(pd, sel)

        painter.setClipRect(QRectF(), Qt.NoClip)
        painter.resetTransform()

    def _paintBorders(self, pd):
        painter = pd.painter

        painter.setPen(self._theme.borderColor)

        # borders between columns
        for column in self._columns:
            painter.drawLine(self._absoluteToWidget(QLineF(column.geometry.right(), 0, column.geometry.right(),
                                                       self.view.height())))

        # header border
        if self.showHeader:
            painter.drawLine(self._absoluteToWidget(QLineF(0, self.headerHeight, self._totalWidth, self.headerHeight)))

    def _wheel(self, event):
        if event.orientation() == Qt.Vertical:
            if event.modifiers() == Qt.NoModifier:
                self.scroll((-event.delta() // 120) * 3)
            elif event.modifiers() == Qt.ControlModifier:
                self.zoom(event.delta() // 120)
        event.accept()

    def scroll(self, row_delta):
        """Delta is number of rows to scroll by. Negative means scroll up, positive - down.
        Scrolls as much rows as possible."""
        if row_delta and self._leadingColumn is not None:
            new_first_row = self.leadingColumn.firstVisibleRow + row_delta
            self.scrollToLeadingColumnRow(new_first_row, correct=True)

    def scrollToLeadingColumnRow(self, first_row, correct=False):
        """Scrolls to given row. If :correct: is True, will adjust too small or too big :first_row: to closest
        allowed values; otherwise will do nothing when :first_row: is invalid.
        """

        if 0 <= self._leadingColumn.dataModel.rowCount() <= first_row:
            if correct:
                first_row = self.leadingColumn.dataModel.rowCount() - 1
            else:
                return
        if first_row < 0:
            if correct:
                first_row = 0
            else:
                return

        self.leadingColumn.scrollToFirstRow(first_row)
        self.syncColumnsFrames()
        self._updateScrollBars()

    def syncColumnsFrames(self, sync_row=0):
        """Forces all columns to be synchronized with leading column at :sync_row:
        """
        for column in self._columns:
            self.syncColumnFrame(column, sync_row)

    def syncColumnFrame(self, column, sync_row=0):
        """Forces column to be scrolled in such a way that :sync_row: (relative to first visible row) of this column
        will contain an index corresponding to first byte of data represented by first index at :sync_row: (relative
        to first visible row too) of leading column. If called for leading column, does nothing.
        """
        if self.leadingColumn is not None and column is not None and column is not self.leadingColumn:
            document_position = self.leadingColumn.frameModel.index(sync_row, 0).data(ColumnModel.DocumentPositionRole)
            if document_position is not None:
                # position frame of non-leading column so same data will be on same row
                sync_index = column.dataModel.indexFromPosition(document_position)
                column_first_row = sync_index.row - sync_row if sync_index.row >= sync_row else 0
                column.scrollToFirstRow(column_first_row)

    def zoom(self, increase):
        if increase:
            new_font_size = self.font().pointSize() + increase
            if 2 <= new_font_size <= 200:
                new_font = QFont(self.font())
                new_font.setPointSize(new_font_size)
                self.setFont(new_font)

    def zoomReset(self):
        self.setFont(appsettings.getFontFromSetting(settings.globalSettings()[appsettings.HexWidget_Font]))

    def isIndexVisible(self, index, full_visible=True):
        """Return True if index is visible in widget. Does not checks if index is invisible due to horizontal
        scroll.
        """
        column = self.columnFromIndex(index)
        if column is not None:
            return bool(column is not None and column.isIndexVisible(index, full_visible))
        return False

    def _resize(self, event):
        for column in self._columns:
            new_geom = column.geometry
            new_geom.setHeight(event.size().height())
            column.geometry = new_geom
        self._updateScrollBars()

    def _updateScrollBars(self):
        should_show = self._shouldShowVScroll
        if should_show:
            lc = self._leadingColumn
            max_value = max(lc.dataModel.realRowCount() - 1, lc.firstVisibleRow)
            self.vScrollBar.maximum = max_value
            self.vScrollBar.pageStep = lc.visibleRows
            # self.vScrollBar.setSingleStepLarge(1)
            self.vScrollBar.value = lc.firstVisibleRow
        self.vScrollBar.setVisible(should_show)

        should_show = self._shouldShowHScroll
        if should_show:
            self.hScrollBar.setRange(0, self._totalWidth - self.view.width())
            self.hScrollBar.setPageStep(self.view.width())
            self.hScrollBar.setSingleStep(10)
            self.hScrollBar.setValue(self._dx)
        self.hScrollBar.setVisible(should_show)

        self.layout().invalidate() # as we change children size inside resizeEvent, layout cannot determine that
                                   # scrollbar has been shown or hidden

    @property
    def _shouldShowVScroll(self):
        lc = self._leadingColumn
        if lc is None:
            return False
        model = lc.dataModel
        return lc.firstVisibleRow > 0 or model.realRowCount() > lc.visibleRows or (0 < model.realRowCount() <= lc.firstVisibleRow)

    @property
    def _shouldShowHScroll(self):
        return self._dx > 0 or self._totalWidth > self.view.width()

    @property
    def _totalWidth(self):
        return sum(column.geometry.width() for column in self._columns)

    def _onVScroll(self, value):
        if self._leadingColumn is not None:
            if value != self._leadingColumn.firstVisibleRow:
                self.scrollToLeadingColumnRow(int(value))

    def _onHScroll(self, value):
        self._dx = value
        self.view.update()

    def _onColumnUpdateRequested(self):
        self.view.update(self.sender().geometry.toRect())

    def _onColumnResizeRequested(self, new_size):
        column_to_resize = self.sender()
        if column_to_resize.geometry.width() != new_size.width():
            column_to_resize.geometry.setWidth(new_size.width())
            self._updateColumnsGeometry()

    def _updateColumnsGeometry(self):
        dx = 0
        for column in self._columns:
            column.geometry.moveLeft(dx)
            dx += column.geometry.width()

        self._updateScrollBars()
        self.view.update()

    _edit_keys = (Qt.Key_Backspace, Qt.Key_Delete)

    def _keyPress(self, event):
        method = None
        if event.key() == Qt.Key_Right:
            if self._activeDelegate is not None:
                self._activeDelegate.handleEvent(event)
            else:
                method = self.NavMethod_NextCell
        elif event.key() == Qt.Key_Left:
            if self._activeDelegate is not None:
                self._activeDelegate.handleEvent(event)
            else:
                method = self.NavMethod_PrevCell
        elif event.key() == Qt.Key_Up:
            method = self.NavMethod_RowUp
        elif event.key() == Qt.Key_Down:
            method = self.NavMethod_RowDown
        elif event.key() == Qt.Key_PageUp:
            method = self.NavMethod_ScreenUp
        elif event.key() == Qt.Key_PageDown:
            method = self.NavMethod_ScreenDown
        elif event.key() == Qt.Key_Home:
            if event.modifiers() & Qt.ControlModifier:
                method = self.NavMethod_DocumentStart
            elif self.editMode:
                self._activeDelegate.handleEvent(event)
            else:
                method = self.NavMethod_RowStart
        elif event.key() == Qt.Key_End:
            if event.modifiers() & Qt.ControlModifier:
                method = self.NavMethod_DocumentEnd
            elif self.editMode:
                self._activeDelegate.handleEvent(event)
            else:
                method = self.NavMethod_RowEnd

        if method is not None:
            self._navigate(method, event.modifiers() & Qt.ShiftModifier)
            return
        else:
            # end keyboard selection
            self._selectStartIndex = None
            self._selectStartColumn = None

        if event.key() == Qt.Key_Tab and event.modifiers() == Qt.NoModifier:
            self.loopLeadingColumn()
            return True
        elif event.key() == Qt.Key_Backtab and event.modifiers() in (Qt.NoModifier, Qt.ShiftModifier):
            self.loopLeadingColumn(reverse=True)
            return True
        elif event.key() == Qt.Key_F2:
            if not self.editMode:
                self.beginEditIndex()
        elif event.key() == Qt.Key_Escape:
            self.endEditIndex(save=False)
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.endEditIndex(save=True)
        elif self.editMode and (event.text() or event.key() in self._edit_keys):
            self._textInputEvent(event)
        elif event.key() == Qt.Key_Insert:
            self._insertMode = not self._insertMode
            self.insertModeChanged.emit(self._insertMode)
        elif event.key() == Qt.Key_Delete and not self.editMode:
            self.deleteSelected()

    def _textInputEvent(self, event):
        if self._activeDelegate is not None:
            delegate = self._activeDelegate
            index_text = None  # new text for index
            nav_method = None  # navigation method that will be performed after modifying text
            cursor_offset = delegate.cursorOffset

            if event.text() and cursor_offset == 0 and self._insertMode and not delegate.insertMode:
                # in insert mode pressing character key when cursor is in beginning of index inserts
                # new index
                self.endEditIndex(save=True)
                self.beginEditNewIndex(event.text(), delegate.index)
            else:
                delegate.handleEvent(event)

    (NavMethod_NextCell, NavMethod_PrevCell, NavMethod_RowStart, NavMethod_RowEnd, NavMethod_ScreenUp,
        NavMethod_ScreenDown, NavMethod_RowUp, NavMethod_RowDown, NavMethod_DocumentStart,
        NavMethod_DocumentEnd) = range(10)

    def _goNextCell(self):
        self._goCaretIndex(self.caretIndex(self._leadingColumn).next)

    def _goPrevCell(self):
        self._goCaretIndex(self.caretIndex(self._leadingColumn).previous)

    def _goRowStart(self):
        self._goCaretIndex(self._leadingColumn.dataModel.index(self.caretIndex(self._leadingColumn).row, 0))

    def _goRowEnd(self):
        index = self.caretIndex(self._leadingColumn)
        self._goCaretIndex(self._leadingColumn.dataModel.lastRowIndex(index.row))

    def _goScreenDown(self):
        self._goByRows(self._leadingColumn.fullVisibleRows - 1)

    def _goScreenUp(self):
        self._goByRows(-(self._leadingColumn.fullVisibleRows - 1))

    def _goRowUp(self):
        self._goByRows(-1)

    def _goRowDown(self):
        self._goByRows(1)

    def _goDocumentStart(self):
        self._goCaretIndex(self._leadingColumn.dataModel.index(0, 0))

    def _goDocumentEnd(self):
        self._goCaretIndex(self._leadingColumn.dataModel.lastRealIndex)

    def _goCaretIndex(self, new_caret_index):
        if not new_caret_index:
            return

        caret_index = self.caretIndex(self._leadingColumn)
        if caret_index.row < new_caret_index.row:
            method = self.MethodShowBottom
        elif caret_index.row > new_caret_index.row:
            method = self.MethodShowTop
        else:
            method = self.MethodShowCenter

        self.makeIndexVisible(new_caret_index, method)

        if new_caret_index != caret_index:
            self.caretPosition = new_caret_index.data(ColumnModel.DocumentPositionRole)

        if self.editMode:
            self._updateCursorOffset()

    def _goByRows(self, row_count):
        caret_index = self.caretIndex(self._leadingColumn)
        if not caret_index:
            return

        data_model = self._leadingColumn.dataModel

        new_row = caret_index.row + row_count
        if data_model.rowCount() >= 0 and new_row >= data_model.rowCount():
            new_row = data_model.rowCount() - 1
        if new_row < 0:
            new_row = 0

        new_caret_index = None
        while not new_caret_index and data_model.hasRow(new_row):
            new_caret_index = data_model.index(new_row, caret_index.column)
            if not new_caret_index:
                new_caret_index = data_model.lastRowIndex(new_row)
            new_row += 1 if row_count > 0 else -1

        self._goCaretIndex(new_caret_index)

    navigate_callbacks = {
        NavMethod_NextCell: _goNextCell,
        NavMethod_PrevCell: _goPrevCell,
        NavMethod_RowStart: _goRowStart,
        NavMethod_RowEnd: _goRowEnd,
        NavMethod_ScreenDown: _goScreenDown,
        NavMethod_ScreenUp: _goScreenUp,
        NavMethod_RowUp: _goRowUp,
        NavMethod_RowDown: _goRowDown,
        NavMethod_DocumentStart: _goDocumentStart,
        NavMethod_DocumentEnd: _goDocumentEnd,
    }

    def _navigate(self, method, make_selection=False):
        old_index = self.caretIndex(self._leadingColumn)
        self.navigate_callbacks[method](self)
        if make_selection:
            new_index = self.caretIndex(self._leadingColumn)
            if old_index:
                # we will not select virtual indexes, but keep selection starting point for them
                if not self._selectStartIndex:
                    self._selectStartIndex = old_index
                    self._selectStartColumn = self.leadingColumn

                if not old_index.virtual and not new_index.virtual:
                    # create selection between stored position and current caret position
                    sel_range = self.selectionBetweenIndexes(new_index, self._selectStartIndex)
                    self.selectionRanges = [sel_range]
            else:
                self._selectStartIndex = None
                self._selectStartColumn = None

    def makeIndexVisible(self, index, method=MethodShowCenter):
        # make caret position full-visible (even if caret is not moved)
        if not self.isIndexVisible(index, True):
            if method == self.MethodShowBottom:
                new_first_row = index.row - self.leadingColumn.fullVisibleRows + 1
            elif method == self.MethodShowTop:
                new_first_row = index.row
            else:
                new_first_row = index.row - int(self.leadingColumn.fullVisibleRows // 2) + 1

            self.scrollToLeadingColumnRow(new_first_row, correct=True)

    def selectionBetweenIndexes(self, first, second):
        if not first or not second:
            return SelectionRange(self)

        first_index = min(first, second)
        last_index = max(first, second)

        return SelectionRange(self, first_index, last_index - first_index + 1, SelectionRange.UnitCells,
                              SelectionRange.BoundToData)

    def columnIndex(self, column):
        index = 0
        for m_column in self._columns:
            if column is m_column:
                return index
            index += 1
        else:
            return -1

    def loopLeadingColumn(self, reverse=False):
        column_index = self.columnIndex(self.leadingColumn)
        if column_index >= 0:
            column_index += -1 if reverse else 1
            if column_index < 0:
                column_index = len(self._columns) - 1
            elif column_index >= len(self._columns):
                column_index = 0

            if 0 <= column_index < len(self._columns):
                if self.editMode:
                    self.endEditIndex(True)
                self.leadingColumn = self._columns[column_index]

    def _mousePress(self, event):
        if event.button() in (Qt.LeftButton, Qt.RightButton):
            mouse_pos = self._widgetToAbsolute(event.posF())
            column = self.columnFromPoint(mouse_pos)
            if column is not None:
                if column is not self.leadingColumn:
                    self.leadingColumn = column

                pos = self._absoluteToColumn(column, mouse_pos)
                activated_index = column.frameModel.toSourceIndex(column.indexFromPoint(pos))
                if activated_index:
                    if self.editMode and activated_index == self.caretIndex(column):
                        # move cursor position to nearest character
                        cursor_offset = max(column.cursorPositionFromPoint(self._absoluteToColumn(column, mouse_pos)), 0)
                        if cursor_offset <= self._activeDelegate.maximalCursorOffset:
                            self._activeDelegate.cursorOffset = cursor_offset
                    else:
                        self.endEditIndex(True)
                        self.caretPosition = activated_index.data(ColumnModel.DocumentPositionRole)

                        if not activated_index.virtual and event.button() == Qt.LeftButton:
                            self._selectStartIndex = activated_index
                            self._selectStartColumn = column
                            self._mousePressPoint = mouse_pos
                elif column.headerRect.contains(pos):
                    # start dragging column
                    self._draggingColumn = column
                    self.setCursor(Qt.ClosedHandCursor)
        event.accept()

    def _mouseRelease(self, event):
        self._selectStartIndex = None
        self._selectStartColumn = None
        self.setCursor(Qt.ArrowCursor)
        if self._draggingColumn is not None:
            if self._columnInsertIndex >= 0:
                self.moveColumn(self._draggingColumn, self._columnInsertIndex)

            self._draggingColumn = None
            self._columnInsertIndex = -1
            self.view.update()
        self._stopScrollTimer()
        event.accept()

    def _mouseMove(self, event):
        mouse_pos = self._widgetToAbsolute(event.posF())
        column = self.columnFromPoint(mouse_pos)
        if self._selectStartIndex:
            if column is not None and column is self._selectStartColumn:
                hover_index = column.indexFromPoint(self._absoluteToColumn(column, mouse_pos))
                if hover_index and hover_index > column.dataModel.lastRealIndex:
                    hover_index = column.dataModel.lastRealIndex

                if hover_index:
                    selections = None

                    # check if current mouse position is close to point where selection was started.
                    # In this case remove selection.
                    if hover_index == self.caretIndex(column):
                        index_rect = self._columnToAbsolute(column, column.rectForIndex(hover_index))
                        hit_rect = QRectF(QPointF(), QSizeF(index_rect.width() // 2, index_rect.height() // 2))
                        hit_rect.moveCenter(self._mousePressPoint)
                        if hit_rect.contains(mouse_pos):
                            selections = []

                    if selections is None:
                        sel = self.selectionBetweenIndexes(self._selectStartIndex, hover_index)
                        if self._selectStartColumn.selectionProxy is not None:
                            proxy = self._selectStartColumn.selectionProxy
                            selection_start = sel.startPosition
                            selection_end = min(self.document.length - 1, selection_start + sel.size - 1)
                            sel = self.selectionBetweenIndexes(proxy.dataModel.indexFromPosition(selection_start),
                                                               proxy.dataModel.indexFromPosition(selection_end))
                        selections = [sel]

                    if selections != self._selections:
                        self.selectionRanges = selections

            self._stopScrollTimer()

            overpos = 0
            if mouse_pos.y() < 0:
                overpos = mouse_pos.y()
            elif mouse_pos.y() > self.view.height():
                overpos = mouse_pos.y() - self.view.height()
            overpos = min(overpos, 100)
            if overpos:
                self._startScrollTimer(math.ceil(overpos / 20))
        elif self._draggingColumn is not None:
            threshold = 15
            if column is None:
                self._columnInsertIndex = len(self._columns)
            else:
                column_pos = self._absoluteToColumn(column, mouse_pos)
                if column_pos.x() <= threshold:
                    self._columnInsertIndex = self.columnIndex(column)
                elif column.geometry.width() - column_pos.x() <= threshold:
                    self._columnInsertIndex = self.columnIndex(column) + 1
            self.view.update()
        event.accept()

    def _mouseDoubleClick(self, event):
        if not self.editMode:
            mouse_pos = self._widgetToAbsolute(event.posF())
            column = self.columnFromPoint(mouse_pos)
            if column is not None:
                index = column.indexFromPoint(self._absoluteToColumn(column, mouse_pos))
                if index.flags & ColumnModel.FlagEditable:
                    self.beginEditIndex()
                    if self.editMode:
                        offset = column.cursorPositionFromPoint(self._absoluteToColumn(column, mouse_pos))
                        self.cursorOffset = min(self._activeDelegate.maximalCursorOffset, max(offset, 0))

    def _startScrollTimer(self, increment):
        self._stopScrollTimer()
        self._scrollTimer = QTimer()
        self._scrollTimer.timeout.connect(lambda: self.scroll(increment))
        self._scrollTimer.start(50)
        self.scroll(increment)

    def _stopScrollTimer(self):
        if self._scrollTimer is not None:
            self._scrollTimer.stop()
            self._scrollTimer = None

    def columnFromPoint(self, point):
        for column in self._columns:
            if column.geometry.contains(point):
                return column
        return None

    def _contextMenu(self, event):
        pos = self._widgetToAbsolute(QPointF(event.pos()))
        column = self.columnFromPoint(pos)
        if column is not None:
            if self._leadingColumn is not column:
                self.leadingColumn = column

        self._actionCopy.setEnabled(self.hasSelection)
        self._actionSetup.setEnabled(column is not None)

        self._contextMenu.popup(event.globalPos())

    def setupActiveColumn(self):
        import hex.columnproviders as columnproviders

        if self._leadingColumn is not None:
            dlg = columnproviders.ConfigureColumnDialog(self, self, self._leadingColumn.dataModel)
            dlg.exec_()

    def _toolTip(self, event):
        pos = self._widgetToAbsolute(QPointF(event.pos()))
        column = self.columnFromPoint(pos)
        if column is not None:
            index = column.indexFromPoint(self._absoluteToColumn(column, pos))
            if index:
                bookmarks = self.bookmarksAtIndex(index)
                tooltip_text = ''
                for bookmark in bookmarks:
                    if tooltip_text:
                        tooltip_text += '\n\n'
                    tooltip_text += utils.tr('Bookmark: {0}').format(bookmark.name)

                if tooltip_text:
                    QToolTip.showText(event.globalPos(), tooltip_text, self)

    def bookmarksAtIndex(self, index):
        if index:
            index_range = DataRange(self, index, 1, DataRange.UnitCells, DataRange.BoundToPosition)
            result = [bookmark for bookmark in self._bookmarks if bookmark.intersectsWith(index_range)]
            return result
        return []

    _eventHandlers = {
        QEvent.Paint: _paint,
        QEvent.Wheel: _wheel,
        QEvent.Resize: _resize,
        QEvent.KeyPress: _keyPress,
        QEvent.MouseButtonPress: _mousePress,
        QEvent.MouseButtonRelease: _mouseRelease,
        QEvent.MouseMove: _mouseMove,
        QEvent.MouseButtonDblClick: _mouseDoubleClick,
        QEvent.ContextMenu: _contextMenu,
        QEvent.ToolTip: _toolTip
    }

    def eventFilter(self, obj, event):
        if obj is self.view:
            handler = self._eventHandlers.get(event.type())
            if handler is not None:
                return bool(handler(self, event))
        return False

    def mousePressEvent(self, event):
        event.accept()

    @property
    def selectionRanges(self):
        return self._selections

    @selectionRanges.setter
    def selectionRanges(self, new_selections):
        if self._selections != new_selections:
            self.clearSelection()
            for sel in new_selections:
                self.addSelectionRange(sel)

    def clearSelection(self):
        while self._selections:
            self.removeSelectionRange(self._selections[0])

    def removeSelectionRange(self, selection):
        sel_index = self._selections.index(selection)
        selection.updated.disconnect(self._onSelectionUpdated)
        del self._selections[sel_index]

        self._checkHasSelectionChanged()
        self.view.update()

    def addSelectionRange(self, selection):
        if selection not in self._selections:
            selection.updated.connect(self._onSelectionUpdated)
            self._selections.append(selection)

            self._checkHasSelectionChanged()
            self.view.update()

    def _onSelectionUpdated(self):
        self._checkHasSelectionChanged()
        self.view.update()

    def _checkHasSelectionChanged(self):
        has_selection = self.hasSelection
        if has_selection != self._hasSelection:
            self._hasSelection = has_selection
            self.hasSelectionChanged.emit(has_selection)

    def beginEditIndex(self, index=None):
        """Starts editing given index. If index is None, caret index of leading column will be edited.
        If another index is being edited at this time, editing of another index is finished, and changes made
        to another index are saved.
        """

        if self.readOnly:
            return

        if index is None:
            index = self.caretIndex(self._leadingColumn)

        if index and index.flags & ColumnModel.FlagEditable:
            if self._activeDelegate is not None:
                if self._activeDelegate.index == index:
                    return
                else:
                    self.endEdit(save=True)

            self._setDelegate(index.model.delegateForIndex(index))
            if self._activeDelegate is not None:
                self._startCursorTimer()

    def beginEditNewIndex(self, input_text, before_index, model=None):
        """Starts editing new index before given one. If :before_index: is invalid (but not None), and :model:
        is not None, last index in given model will be edited. If another index is being editing,
        changes will be saved.
        """

        if self.readOnly or self.fixedSize or before_index is None:
            return

        model = before_index.model if before_index else model
        if model is None:
            return

        self.endEditIndex(save=True)

        self._setDelegate(model.delegateForNewIndex(input_text, before_index))
        if self._activeDelegate is not None:
            self._startCursorTimer()

    def _setDelegate(self, delegate):
        if self._activeDelegate is not delegate:
            if self._activeDelegate is not None:
                pass
            if delegate is not None:
                self.caretPosition = delegate.index.documentPosition
            self._activeDelegate = delegate
            if delegate is not None:
                delegate.finished.connect(self._onDelegateFinished)
                delegate.cursorMoved.connect(self._updateCursorOffset)
                delegate.requestFinish.connect(self._onDelegateFinishRequested)
            for column in self._columns:
                column.frameModel.activeDelegate = delegate

    def _onDelegateFinished(self):
        self._setDelegate(None)

        # and stop cursor update timer
        self._cursorVisible = False
        self._cursorTimer.stop()
        self._cursorTimer = None

        self.view.update()

    def _onDelegateFinishRequested(self, save, next_index):
        if self._activeDelegate is self.sender():
            delegate = self._activeDelegate
            if next_index == StandardEditDelegate.EditNextIndex and not delegate.hasNextEditIndex:
                return
            elif next_index == StandardEditDelegate.EditPreviousIndex and not delegate.hasPreviousEditIndex:
                return

            self.endEditIndex(save)

            if next_index == StandardEditDelegate.EditNextIndex:
                self.beginEditIndex(delegate.nextEditIndex)
            elif next_index == StandardEditDelegate.EditPreviousIndex:
                self.beginEditIndex(delegate.previousEditIndex)

    def _startCursorTimer(self):
        """Starts timer that updates blinking cursor"""
        self._cursorVisible = True
        self._cursorTimer = QTimer()
        self._cursorTimer.timeout.connect(self._toggleCursor)
        self._cursorTimer.start(QApplication.cursorFlashTime())
        self.view.update()

    def endEditIndex(self, save):
        """Ends editing of current index. If no indexes are being edited, does nothing. Optionally saves changes.
        """

        if self._activeDelegate is not None:
            self._activeDelegate.end(save)

    def selectAll(self):
        if self.document is not None and self._leadingColumn is not None:
            first_index = self._leadingColumn.dataModel.firstIndex
            last_index = self._leadingColumn.dataModel.lastRealIndex
            if first_index and last_index:
                sel_range = SelectionRange(self, first_index, last_index - first_index + 1,
                                           SelectionRange.UnitCells, SelectionRange.BoundToData)
                self.selectionRanges = [sel_range]

    def copyAsData(self):
        if len(self._selections) == 1:
            documents.Clipboard.setData(self.document, self._selections[0].startPosition, self._selections[0].size)

    def copyAsText(self):
        if self._leadingColumn is not None and len(self._selections) and self._selections[0]:
            selection = self._selections[0]
            first_index = self._leadingColumn.dataModel.indexFromPosition(selection.startPosition)
            last_index = self._leadingColumn.dataModel.indexFromPosition(selection.startPosition + selection.size - 1)
            if first_index and last_index and last_index > first_index:
                sep = ' ' if self._leadingColumn.spaced else ''

                if first_index.column:
                    first_row_index = self._leadingColumn.dataModel.index(first_index.row, 0)
                    text = sep.join(' ' * len(index.data()) for index in index_range(first_row_index, first_index))
                    text += sep
                else:
                    text = ''

                text += sep.join('\n' * int(not index.column) + index.data() for index in index_range(first_index,
                                                                                                      last_index,
                                                                                                      include_last=True))
                if text.startswith('\n'):
                    text = text[len('\n'):]
                text = text.replace(' \n', '\n')

                QApplication.clipboard().setText(text)

    def pasteAsData(self):
        if 0 <= self.caretPosition < self._document.length:
            chain = documents.Clipboard.getData()
            if not utils.isNone(chain):
                self.document.insertChain(self.caretPosition, chain)

    def pasteAsText(self):
        if self._leadingColumn is not None and not self.readOnly and not self.fixedSize and self._leadingColumn:
            if not (0 <= self.caretPosition < self._document.length):
                return
            text = QApplication.clipboard().mimeData().text()
            if text:
                data = self._leadingColumn.dataModel.parseTextInput(text)
                if data:
                    self._document.insertSpan(self.caretPosition, documents.DataSpan(data))

    def paste(self):
        if 0 < self.caretPosition < self._document.length:
            if documents.Clipboard.hasBinaryData():
                self.pasteAsData()
            else:
                if not QApplication.clipboard().mimeData().hasText():
                    return

                # ask user if he want to insert this as data or text...
                msgbox = QMessageBox(self)
                msgbox.setWindowTitle(utils.tr('Paste from clipboard'))
                msgbox.setText(utils.tr('Clipboard contains text data - do you want to interpret it as plain '
                                        'hex values (like "aa bb cc") and insert raw data or insert data in '
                                        'format specific for current column?'))
                msgbox.setIcon(QMessageBox.Question)
                button_as_data = msgbox.addButton(utils.tr('As raw data'), QMessageBox.AcceptRole)
                button_as_text = msgbox.addButton(utils.tr('As text'), QMessageBox.AcceptRole)
                msgbox.addButton(QMessageBox.Cancel)
                msgbox.setDefaultButton(QMessageBox.Cancel)
                if msgbox.exec_() == QMessageBox.Accepted:
                    if msgbox.standardButton(msgbox.clickedButton()) == QMessageBox.Cancel:
                        return
                    if msgbox.clickedButton() is button_as_data:
                        self.pasteAsData()
                    else:
                        self.pasteAsText()

    def undo(self):
        try:
            self.document.undo()
        except IOError:
            pass

    def canUndo(self):
        return self.document.canUndo()

    def canRedo(self):
        return self.document.canRedo()

    def redo(self, branch=-1):
        try:
            self.document.redo(branch)
        except IOError:
            pass

    def deleteSelected(self):
        """Deletes all bytes that are selected"""
        if not self._document.readOnly and not self._document.fixedSize:
            self._document.beginComplexAction()
            try:
                for selection in self._selections:
                    self._document.remove(selection.startPosition, selection.size)
            finally:
                self._document.endComplexAction()

    @property
    def showHeader(self):
        return self._showHeader

    @showHeader.setter
    def showHeader(self, show):
        if self._showHeader != show:
            self._showHeader = show
            for column in self._columns:
                column.showHeader = show
            self.showHeaderChanged.emit(show)

    def _adjustHeaderHeights(self):
        header_height = max(column.idealHeaderHeight() for column in self._columns)
        for column in self._columns:
            column.headerHeight = header_height

    @property
    def headerHeight(self):
        return self._columns[0].headerHeight if self._columns else 0

    def _paintCursor(self, pd):
        if self.editMode and self._cursorVisible and self.isIndexVisible(self.caretIndex(self._leadingColumn)):
            cursor_pos = self._absoluteToWidget(self._cursorPosition())
            font_metrics = QFontMetricsF(self.font())
            line_height = font_metrics.height()
            if self._blockCursor:
                try:
                    char_under_cursor = self.caretIndex(self._leadingColumn).data()[self._activeDelegate.cursorOffset]
                except IndexError:
                    return
                cursor_width = font_metrics.width(char_under_cursor)
                pd.painter.setBrush(self._theme.cursorBackgroundColor)
                pd.painter.setPen(self._theme.cursorBorderColor)
                pd.painter.drawRect(QRectF(cursor_pos, QSizeF(cursor_width, line_height)))
            else:
                pd.painter.setPen(QPen(self._theme.cursorBorderColor, 1.0))
                pd.painter.drawLine(cursor_pos, QPointF(cursor_pos.x(), cursor_pos.y() + line_height))

    def _cursorPosition(self):
        caret_index = self.caretIndex(self._leadingColumn)
        if self.editMode and self._cursorVisible and self.isIndexVisible(caret_index):
            return self._columnToAbsolute(self._leadingColumn,
                                          self._leadingColumn.cursorPositionInIndex(caret_index, self._activeDelegate.cursorOffset))
        return QPointF()

    def _toggleCursor(self):
        if self.editMode:
            self._cursorVisible = not self._cursorVisible
        else:
            self._cursorVisible = True
        self.view.update()

    def findNextEditableIndex(self, from_index):
        if not from_index:
            return from_index
        return from_index.model.nextEditIndex(from_index)

    def findPreviousEditableIndex(self, from_index):
        return from_index.model.previousEditIndex(from_index)

    def _updateCursorOffset(self):
        if self._cursorTimer is not None:
            self._cursorTimer.stop()
        self._cursorVisible = True
        if self._cursorTimer is not None:
            self._cursorTimer.start(QApplication.cursorFlashTime())
        self.view.update()

    @property
    def insertMode(self):
        return self._insertMode

    @insertMode.setter
    def insertMode(self, mode):
        if self._insertMode != mode:
            self._insertMode = mode
            self.insertModeChanged.emit(mode)

    def removeSelected(self):
        for selection in self._selections:
            self.document.remove(selection.startPosition, selection.size)

    def fillSelected(self, fill_byte):
        for selection in self._selections:
            self.document.writeSpan(selection.startPosition, documents.FillSpan(selection.size, fill_byte))
        self.view.update()

    def removeActiveColumn(self):
        if self._leadingColumn is not None:
            self._columns = [c for c in self._columns if c is not self._leadingColumn]
            self.leadingColumn = self._columns[0] if self._columns else None
            self._updateColumnsGeometry()

    def addAddressColumn(self, address_column_model, relative_position=Qt.AlignLeft):
        """Adds address column to leading one. relative_position can be Qt.AlignLeft or Qt.AlignRight
        and determines where address column will be located.
        """
        if self._leadingColumn is not None:
            leading_column_index = self.columnIndex(self._leadingColumn)
            if relative_position == Qt.AlignLeft:
                column_index = leading_column_index
            else:
                column_index = leading_column_index + 1
            address_column_model.linkedModel = self._leadingColumn.dataModel
            self.insertColumn(address_column_model, column_index)

    @property
    def hasSelection(self):
        return bool(self._selections) and any(bool(sel) for sel in self._selections)

    @property
    def readOnly(self):
        return self.document.readOnly if self.document is not None else True

    @property
    def fixedSize(self):
        return self.document.fixedSize if self.document is not None else False

    @property
    def isModified(self):
        return self.document.modified if self.document is not None else False

    def save(self, device=None, switch_to_device=False):
        if self.document is not None:
            self.document.save(device, switch_to_device)
            self.reset()

    def reset(self):
        for column in self._columns:
            column.dataModel.reset()

    @property
    def url(self):
        return self.document.url if self.document is not None else QUrl()

    def goto(self, position):
        if self._leadingColumn is not None:
            self.caretPosition = position
            self.makeIndexVisible(self.caretIndex(self._leadingColumn), self.MethodShowCenter)

    @property
    def bookmarks(self):
        return self._bookmarks

    def addBookmark(self, bookmark):
        if bookmark is not None and bookmark not in self._bookmarks:
            self._bookmarks.append(bookmark)
            self._bookmarks.sort(key=lambda x: x.size, reverse=True)
            bookmark.updated.connect(self._updateBookmark)
            self.view.update()

    def removeBookmark(self, bookmark):
        bookmark_index = self._bookmarks.index(bookmark)
        bookmark.updated.disconnect(self._updateBookmark)
        del self._bookmarks[bookmark_index]
        self.view.update()

    def _updateBookmark(self):
        self.view.update()

    def isRangeDataVisible(self, data_range):
        return any(c.isRangeVisible(data_range) for c in self._columns)

    @property
    def theme(self):
        return self._theme

    def emphasize(self, emp_range):
        if self._emphasizeRange is not None:
            self._removeEmphasize(self._emphasizeRange)

        self._emphasizeRange = emp_range
        self._emphasizeRange.updated.connect(self.view.update)
        self._emphasizeRange.finished.connect(self._onEmphasizeFinished)

        # make emphasized range visible
        if self._leadingColumn is not None:
            index = self._leadingColumn.dataModel.indexFromPosition(emp_range.startPosition)
            if index:
                self.makeIndexVisible(index, self.MethodShowTop)

        self._emphasizeRange.emphasize()

    def _onEmphasizeFinished(self):
        self._removeEmphasize(self.sender())

    def _removeEmphasize(self, emp_range):
        self._emphasizeRange = None
        emp_range.updated.disconnect(self.view.update)
        emp_range.finished.disconnect(self._onEmphasizeFinished)


class DataRange(QObject):
    """DataRange can be based on bytes or on cells. When based on bytes, size of range always remains the same, and
    when based on cells, size is automatically adjusted when column data is changed to always represent data occupied
    by given number of cells.
    Also DataRange can be bound to data or to positions. When bound to positions, range always will start at given position
    despite document data modifications. When bound to data, inserting or removing data before range start shifts range
    start position; removing data inside range leads to collapsing range size.
    """

    UnitBytes, UnitCells = range(2)
    BoundToData, BoundToPosition = range(2)

    moved = pyqtSignal(object, object)
    resized = pyqtSignal(object, object)
    updated = pyqtSignal()

    def __init__(self, hexwidget, start=-1, length=0, unit=UnitBytes, bound_to=BoundToData):
        """When unit == UnitBytes, start should be document position (int), if unit == UnitCells, start should be ModelIndex
        """
        QObject.__init__(self)
        self._hexWidget = hexwidget
        self._start = start.offset if unit == self.UnitCells else start
        self._length = length
        self._unit = unit
        self._boundTo = bound_to
        self._model = start.model if unit == self.UnitCells else None
        self._size = self._getSize()

        if bound_to == self.BoundToData:
            if unit == self.UnitBytes:
                self._hexWidget.document.bytesInserted.connect(self._onInserted, Qt.QueuedConnection)
                self._hexWidget.document.bytesRemoved.connect(self._onRemoved, Qt.QueuedConnection)
            else:
                self._model.indexesInserted.connect(self._onInserted)
                self._model.indexesRemoved.connect(self._onRemoved)

        if unit == self.UnitCells:
            self._model.dataChanged.connect(self._onIndexesDataChanged)

        self.moved.connect(self.updated)
        self.resized.connect(self.updated)

    @property
    def start(self):
        return self._model.indexFromOffset(self._start) if self._unit == self.UnitCells else self._start

    @start.setter
    def start(self, new_start):
        if self.start != new_start:
            old_pos = self._start
            old_start = self.start
            self._start = new_start.offset if self._unit == self.UnitCells else new_start
            self.moved.emit(new_start, old_start)

    @property
    def startPosition(self):
        if not self.valid:
            return -1
        elif self._unit == self.UnitBytes:
            return self._start
        else:
            pos = self.start.data(ColumnModel.DocumentPositionRole)
            return pos if pos is not None else -1

    @property
    def length(self):
        return self._length

    @length.setter
    def length(self, new_len):
        if self._length != new_len:
            old_size = self._size
            self._length = new_len
            self._size = self._getSize()
            if self._size != old_size:
                self.resized.emit(self._size, old_size)

    @property
    def size(self):
        return self._size

    @property
    def valid(self):
        return self._start >= 0

    @property
    def unit(self):
        return self._unit

    @property
    def boundTo(self):
        return self._boundTo

    def __bool__(self):
        return self.valid and bool(self.length)

    def _getSize(self):
        if not self.valid:
            return 0
        elif self._unit == self.UnitBytes:
            return self._length
        else:
            first_index = self._model.indexFromOffset(self._start)
            last_index = self._model.indexFromOffset(self._start + self._length - 1)
            if last_index:
                last_pos = last_index.data(ColumnModel.DocumentPositionRole) + last_index.data(ColumnModel.DataSizeRole)
                return last_pos - first_index.data(ColumnModel.DocumentPositionRole)
            elif first_index:
                return self._model.document.length - first_index.data(ColumnModel.DocumentPositionRole)
        return 0

    def _onInserted(self, start, length):
        if self._boundTo == self.BoundToData and self.valid:
            assert(bool(start) and length >= 0)
            if start <= self.start:
                # inserted before range start, shift it right
                self.start += length
            elif self.start < start < self.start + self.length:
                # inserted inside range, expand it
                self.length += length

    def _onRemoved(self, start, length):
        if self._boundTo == self.BoundToData and self.valid:
            # if unit == UnitCells, start can be invalid ModelIndex (in cases where indexes removed
            # from beginning of model), otherwise it is index BEFORE which indexes was removed.
            if self._unit == self.UnitCells:
                start = 0 if not start else start.offset + 1

            if start < self._start:
                # removed before range begin
                old_start = self.start
                self._start = max(start, self._start - length)
                if old_start != self.start:
                    self.moved.emit(self.start, old_start)
                if start + length > self._start:
                    length_dec = length + start - self._start
                    self.length = max(0, self._length - length_dec)
            elif self._start <= start < self._start + self._length:
                left = start - self._start
                right = max(0, (self._start + self._length) - (start + length))
                self.length = left + right

    def _onIndexesDataChanged(self, first_index, last_index):
        if self._boundTo == self.BoundToData and self._unit == self.UnitCells and self.valid and self.length > 0:
            if not (first_index > self.start + self.length or last_index < self.start):
                old_size = self._size
                self._size = self._getSize()
                if old_size != self._size:
                    self.resized.emit(self._size, old_size)

    def __eq__(self, other):
        if not isinstance(other, DataRange):
            return NotImplemented
        return (self._unit == other._unit and self._start == other._start and self._length == other._length and
                    self._boundTo == other._boundTo)

    def intersectsWith(self, another_range):
        return not (another_range.startPosition >= self.startPosition + self.size or
                    another_range.startPosition + another_range.size <= self.startPosition)

    def contains(self, another_range):
        return (another_range.startPosition >= self.startPosition and another_range.startPosition + another_range.size
                        < self.startPosition + self.size)


class SelectionRange(DataRange):
    pass


class HighlightedRange(DataRange):
    def __init__(self, hexwidget, start=-1, length=0, unit=DataRange.UnitBytes, bound_to=DataRange.BoundToData):
        DataRange.__init__(self, hexwidget, start, length, unit, bound_to)
        self._backgroundColor = None

    @property
    def backgroundColor(self):
        return self._backgroundColor

    @backgroundColor.setter
    def backgroundColor(self, new_color):
        if self._backgroundColor != new_color:
            self._backgroundColor = new_color
            self.updated.emit()


class BookmarkedRange(HighlightedRange):
    def __init__(self, hexwidget, start=-1, length=0, unit=DataRange.UnitBytes, bound_to=DataRange.BoundToData):
        HighlightedRange.__init__(self, hexwidget, start, length, unit, bound_to)
        self._name = ''

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_name):
        if self._name != new_name:
            self._name = new_name
            self.updated.emit()

    @property
    def innerLevel(self):
        return self.name.count('.')


class EmphasizedRange(HighlightedRange):
    finished = pyqtSignal()

    def alpha(self):
        return self._backgroundColor.alpha()

    def setAlpha(self, alpha):
        if alpha > 255:
            alpha = 255
        elif alpha < 0:
            alpha = 0
        self._backgroundColor.setAlpha(alpha)
        self.updated.emit()

    alpha = pyqtProperty('int', alpha, setAlpha)

    def __init__(self, hexwidget, start=-1, length=0, unit=DataRange.UnitBytes, bound_to=DataRange.BoundToData):
        HighlightedRange.__init__(self, hexwidget, start, length, unit, bound_to)
        self.backgroundColor = QColor(Qt.red)

        self._animation = QSequentialAnimationGroup(self)
        animation1 = QPropertyAnimation(self, 'alpha', self)
        animation1.setStartValue(0)
        animation1.setEndValue(255)
        animation1.setDuration(600)
        animation1.setEasingCurve(QEasingCurve(QEasingCurve.Linear))
        self._animation.addAnimation(animation1)
        animation2 = QPropertyAnimation(self, 'alpha', self)
        animation2.setStartValue(255)
        animation2.setEndValue(0)
        animation2.setDuration(600)
        animation2.setEasingCurve(QEasingCurve(QEasingCurve.Linear))
        animation2.setDirection(QPropertyAnimation.Backward)
        self._animation.addAnimation(animation2)
        self._animation.finished.connect(self.finished)

    def emphasize(self):
        self._animation.start()
