from PyQt4.QtCore import pyqtSignal, QObject, Qt, QPointF, QRectF, QPoint, QSizeF, QEvent, QTimer, QLineF, QUrl
from PyQt4.QtGui import QColor, QFont, QFontMetricsF, QPolygonF, QWidget, QScrollBar, QVBoxLayout, QHBoxLayout, \
                        QPainter, QBrush, QPalette, QPen, QApplication, QRegion, QLineEdit, QValidator, \
                        QTextEdit, QTextOption, QSizePolicy, QStyle, QStyleOptionFrameV2, QTextCursor, QTextDocument, \
                        QTextBlockFormat, QPlainTextDocumentLayout, QAbstractTextDocumentLayout, QTextCharFormat, \
                        QTextTableFormat, QRawFont, QKeyEvent, QFontDatabase, QMenu
import math
import html
from hex.valuecodecs import IntegerCodec
from hex.formatters import IntegerFormatter
from hex.editor import DataSpan, FillSpan
from hex.proxystyle import ProxyStyle
import hex.encodings as encodings
import hex.utils as utils
import hex.settings as settings
import hex.appsettings as appsettings


# Why we need to make different model/view classes? Why not to use existing ones?
# These classes are specialized and optimized for our needs. But main cause is that standard model classes will not
# work with very big amount of data (especially on 32-bit machines) where number of rows exceeds 32-bit int limit.
# Another difference is that custom model class represents irregular array instead of tree-like structure Qt does.


class ModelIndex(object):
    def __init__(self, row=-1, column=-1, model=None, internal_data=None):
        self.__row = row
        self.__column = column
        self.__model = model
        self.__data = internal_data

    @property
    def row(self):
        """This value is always positive int for valid indexes, -1 otherwise"""
        return self.__row if self.valid else -1

    @property
    def column(self):
        """This value is always positive int for valid indexes, -1 otherwise"""
        return self.__column if self.valid else -1

    @property
    def model(self):
        """Returns model this index belongs to, None for invalid indexes"""
        return self.__model if self.valid else None

    @property
    def virtual(self):
        # virtual indexes does not represent real data, but used to represent empty cells in regular models.
        # Regular model has finite set of not-virtual indexes and can have infinite set of virtual ones
        return self.flags & ColumnModel.FlagVirtual

    @property
    def valid(self):
        """Return True if index is valid"""
        return self.__model is not None and self.__row >= 0 and self.__column >= 0

    @property
    def internalData(self):
        return self.__data if self.valid else None

    def data(self, role=Qt.DisplayRole):
        """Data for index"""
        return self.__model.indexData(self, role) if self.valid else None

    def setData(self, value, role=Qt.EditRole):
        self.__model.setIndexData(self, value, role)

    @property
    def flags(self):
        return self.__model.indexFlags(self) if self.valid else 0

    def __eq__(self, other):
        """Invalid index is not equal to any index"""
        if not isinstance(other, ModelIndex):
            return NotImplemented
        return (self.valid and other.valid and self.row == other.row and self.column == other.column
                and self.model is other.model)

    def __ne__(self, other):
        if not isinstance(other, ModelIndex):
            return NotImplemented
        return not self.__eq__(other)

    def __bool__(self):
        return self.valid

    def __isCompatible(self, other):
        return isinstance(other, ModelIndex) and self.valid and other.valid

    def __lt__(self, other):
        if not self.__isCompatible(other):
            return NotImplemented
        return self.row < other.row or (self.row == other.row and self.column < other.column)

    def __gt__(self, other):
        if not self.__isCompatible(other):
            return NotImplemented
        return self.row > other.row or (self.row == other.row and self.column > other.column)

    def __le__(self, other):
        if not self.__isCompatible(other):
            return NotImplemented
        return self.__lt__(other) or self.__eq__(other)

    def __ge__(self, other):
        if not self.__isCompatible(other):
            return NotImplemented
        return self.__gt__(other) or self.__eq__(other)

    @property
    def next(self):
        if not self.valid:
            return ModelIndex()

        next_index = self.model.index(self.row, self.column + 1)
        if not next_index:
            row = self.row + 1
            while not next_index and (self.model.rowCount() < 0 or row < self.model.rowCount()):
                next_index = self.model.index(row, 0)
                row += 1

        return next_index

    @property
    def previous(self):
        if not self.valid:
            return ModelIndex()

        prev_index = self.model.index(self.row, self.column - 1)
        if not prev_index:
            row = self.row - 1
            while not prev_index and row >= 0:
                prev_index = self.model.lastRowIndex(row)
                row -= 1

        return prev_index


class ColumnModel(QObject):
    EditorDataRole = Qt.UserRole + 1
    EditorPositionRole = Qt.UserRole + 2
    DataSizeRole = Qt.UserRole + 3

    FlagVirtual = 1
    FlagEditable = 2
    FlagModified = 4

    dataChanged = pyqtSignal(ModelIndex, ModelIndex)
    dataResized = pyqtSignal(ModelIndex)  # argument is new last real index
    modelReset = pyqtSignal()

    def __init__(self, editor=None):
        QObject.__init__(self)
        self.name = ''
        self.__editor = None
        self.editor = editor

    @property
    def editor(self):
        return self.__editor

    @editor.setter
    def editor(self, new_editor):
        if self.__editor is not new_editor:
            if self.__editor is not None:
                with self.__editor.lock:
                    self.__editor.dataChanged.disconnect(self.onEditorDataChanged)
                    self.__editor.resized.disconnect(self.onEditorDataResized)
                self.__editor = None

            self.__editor = new_editor
            if new_editor is not None:
                with new_editor.lock:
                    new_editor.dataChanged.connect(self.onEditorDataChanged, Qt.QueuedConnection)
                    new_editor.resized.connect(self.onEditorDataResized, Qt.QueuedConnection)

    def reset(self):
        self.modelReset.emit()

    def rowCount(self):
        """Should return -1 if model has infinite number of rows."""
        raise NotImplementedError()

    def realRowCount(self):
        """Should return positive integer, infinite number of real rows is not allowed"""
        return self.rowCount()

    def columnCount(self, row):
        """Should return -1 if no row exists"""
        raise NotImplementedError()

    def realColumnCount(self, row):
        return self.columnCount(row)

    def index(self, row, column):
        """Create index for row and column. Can return virtual index"""
        return ModelIndex(row, column, self) if self.hasIndex(row, column) else ModelIndex()

    def lastRowIndex(self, row):
        """Return last index on given row."""
        return self.index(row, self.columnCount(row) - 1)

    def lastRealRowIndex(self, row):
        return self.index(row, self.realColumnCount(row) - 1)

    def indexFlags(self, index):
        return 0

    def indexData(self, index, role=Qt.DisplayRole):
        return None

    def headerData(self, section, role=Qt.DisplayRole):
        # this is standard header data. It works only for regular columns and displays offset from start of the row.
        if self.regular and role == Qt.DisplayRole:
            if 0 <= section <= self.columnCount(0):
                cell_offset = self.index(0, section).data(self.EditorPositionRole)
                return IntegerFormatter(base=16).format(cell_offset)

    def hasIndex(self, row, column):
        """Return True if there is index at row and column in this model"""
        if self.rowCount() < 0 or row < self.rowCount():
            return column < self.columnCount(row)
        return False

    def hasRealIndex(self, row, column):
        return row < self.realRowCount() and column < self.realColumnCount(row)

    def hasRow(self, row):
        return row >= 0 and (self.rowCount() < 0 or row + 1 < self.rowCount())

    @property
    def firstIndex(self):
        return self.index(0, 0)

    @property
    def lastIndex(self):
        """Return last index in the model"""
        if self.rowCount() <= 0:
            return ModelIndex()

        row = self.rowCount() - 1
        index = ModelIndex()
        while not index and row >= 0:
            index = self.lastRowIndex(row)
            row += 1
        return index

    @property
    def lastRealIndex(self):
        row = self.realRowCount() - 1
        index = ModelIndex()
        while not index and row >= 0:
            index = self.lastRealRowIndex(row)
            row -= 1
        return index

    def setIndexData(self, index, value, role=Qt.EditRole):
        return False

    def onEditorDataChanged(self, start, length):
        pass

    def onEditorDataResized(self, new_size):
        pass

    @property
    def preferSpaced(self):
        """Whether view should display indexes with spaces between them by default"""
        return True

    def indexFromPosition(self, position):
        """Return index matching given editor position. Can return virtual index"""
        raise NotImplementedError()

    @property
    def regular(self):
        """Return True if this model is regular. Regular models have same number of columns in each row and same
        text length for cell."""
        return False

    def defaultIndexData(self, before_index, role=Qt.EditRole):
        """Returns data for index that should be inserted before given cell (or after last index
        if :before_index: is invalid) when any character is typed in while in insert mode.
        It is enough for method to support only Qt.EditRole and ColumnModel.EditorDataRole roles.
        """
        raise NotImplementedError()

    def insertIndex(self, before_index):
        """Insert data for new default index just before :before_index: or at the end of model if :before_index:
        is invalid and model does not support virtual indexes. Should return new index"""
        pos = before_index.data(self.EditorPositionRole)
        if pos >= 0:
            data_to_insert = self.defaultIndexData(before_index, self.EditorDataRole)
            if data_to_insert:
                self.editor.insertSpan(pos, DataSpan(self.editor, data_to_insert))
                return self.indexFromPosition(pos)
        raise ValueError('failed to insert index before given one')

    def createValidator(self):
        return None


def index_range(start_index, end_index, include_last):
    """Iterator allows traversing through model indexes."""
    if not start_index or not end_index or end_index < start_index:
        return
    current_index = start_index
    while current_index:
        if include_last and not (current_index <= end_index):
            break
        elif not include_last and not (current_index < end_index):
            break
        yield current_index
        current_index = current_index.next


class EmptyColumnModel(ColumnModel):
    def rowCount(self):
        return 0

    def columnCount(self, row):
        return 0

    def indexFromPosition(self, position):
        return ModelIndex()


class FrameProxyModel(ColumnModel):
    """This proxy model displays only number of rows starting after given first row. Proxy model does not check
    if there are indexes on these rows."""

    frameScrolled = pyqtSignal(int, int)  # first argument is new first frame row, second one is old first frame row
    frameResized = pyqtSignal(int, int)  # first argument is new frame size, second one is old frame size

    def __init__(self, source_model):
        ColumnModel.__init__(self, None)
        self.__firstRow = 0
        self.__rowCount = 0
        self.sourceModel = source_model or EmptyColumnModel()
        self.sourceModel.dataChanged.connect(self.__onDataChanged)
        self.sourceModel.dataResized.connect(self.__onDataResized)
        self.sourceModel.modelReset.connect(self.modelReset)

    def setFrame(self, first_row, row_count):
        self.resizeFrame(row_count)
        self.scrollFrame(first_row)

    def scrollFrame(self, new_first_row):
        if self.__firstRow != new_first_row:
            old_first_row = self.__firstRow
            self.__firstRow = new_first_row
            self.frameScrolled.emit(new_first_row, old_first_row)

    def resizeFrame(self, new_frame_size):
        if self.__rowCount != new_frame_size:
            old_size = self.__rowCount
            self.__rowCount = new_frame_size
            self.frameResized.emit(new_frame_size, old_size)

    def rowCount(self):
        model_row_count = self.sourceModel.rowCount()
        if model_row_count >= 0:
            return min(self.__rowCount, model_row_count)
        else:
            return self.__rowCount

    def columnCount(self, row):
        return self.sourceModel.columnCount(row + self.__firstRow)

    def realRowCount(self):
        return min(self.__rowCount, self.sourceModel.rowCount())

    def realColumnCount(self, row):
        return self.sourceModel.realColumnCount(row + self.__firstRow)

    def indexFromPosition(self, position):
        return self.fromSourceIndex(self.sourceModel.indexFromPosition(position))

    def index(self, row, column=0):
        return self.fromSourceIndex(self.sourceModel.index(row + self.__firstRow, column))

    def hasIndex(self, row, column):
        return ColumnModel.hasIndex(self, row, column) and self.sourceModel.hasIndex(row + self.__firstRow, column)

    def hasRealIndex(self, row, column):
        return ColumnModel.hasIndex(self, row, column) and self.sourceModel.hasRealIndex(row + self.__firstRow, column)

    def indexData(self, index, role=Qt.DisplayRole):
        return self.sourceModel.indexData(self.toSourceIndex(index), role)

    def indexFlags(self, index):
        return self.sourceModel.indexFlags(self.toSourceIndex(index))

    def setIndexData(self, index, value, role=Qt.EditRole):
        return self.sourceModel.setIndexData(self.toSourceIndex(index), value, role)

    def headerData(self, section, role=Qt.DisplayRole):
        return self.sourceModel.headerData(section, role)

    def toSourceIndex(self, index):
        if not index or index.model is self.sourceModel:
            return index
        elif self.hasIndex(index.row, index.column):
            return self.sourceModel.index(index.row + self.__firstRow, index.column)
        else:
            return ModelIndex()

    def fromSourceIndex(self, index):
        if not index or index.model is self:
            return index
        elif self.hasIndex(index.row - self.__firstRow, index.column):
            return ModelIndex(index.row - self.__firstRow, index.column, self)
        else:
            return ModelIndex()

    def __onDataChanged(self, first, last):
        # check if update area lays inside frame
        if last.row < self.__firstRow or first.row > self.toSourceIndex(self.lastIndex).row:
            return

        first = self.fromSourceIndex(first) or self.firstIndex
        last = self.fromSourceIndex(last) or self.lastIndex

        self.dataChanged.emit(first, last)

    def __onDataResized(self, new_last_index):
        self.modelReset.emit()

    @property
    def regular(self):
        return self.sourceModel.regular


class Theme(object):
    def __init__(self):
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
        self.headerBackgroundColor = self.backgroundColor
        self.headerTextColor = self.textColor
        self.headerInactiveTextColor = self.inactiveTextColor
        self.alternateRowColor = QColor(225, 225, 210)

    def load(self, settings, name):
        theme_obj = settings[name]
        for key in theme_obj.keys():
            attr = utils.underscoreToCamelCase(key)
            if not hasattr(self, attr) or not callable(getattr(self, attr)):
                stored_value = theme_obj[key]
                if isinstance(stored_value, str):
                    color = self.colorFromName(theme_obj[key])
                    if color.isValid():
                        setattr(self, attr, color)

    def save(self, settings, name):
        theme_obj = dict()
        for attr_name in dir(self):
            if not attr_name.startswith('_') and isinstance(getattr(self, attr_name), QColor):
                color = getattr(self, attr_name)
                color_name = color.name()
                if color.alpha() != 255:
                    color_name += ':' + str(color.alpha())
                theme_obj[utils.camelCaseToUnderscore(attr_name)] = color_name
        settings[name] = theme_obj

    @staticmethod
    def colorFromName(name):
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


VisualSpace = 10
DefaultTheme = None


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

    @property
    def text(self):
        return self.data()

    def data(self, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if self._text is None:
                self._text = self.index.data()
            return self._text
        if self.index:
            return self.index.data(role)
        return None


class ColumnDocumentBackend(QObject):
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

    def rectForCell(self, row_index, cell_index):
        raise NotImplementedError()

    def cursorPositionInCell(self, row_index, cell_index, cursor_offset):
        raise NotImplementedError()

    def cellFromPoint(self, point):
        raise NotImplementedError()

    def cursorPositionFromPoint(self, point):
        raise NotImplementedError()

    def clear(self):
        self._document = None


class PlainTextDocumentBackend(ColumnDocumentBackend):
    def __init__(self, column):
        ColumnDocumentBackend.__init__(self, column)

    def generateDocument(self):
        if self._document is None:
            self._document = self._column.createDocumentTemplate()

            cursor = QTextCursor(self._document)
            block_format = self._documentBlockFormat
            for row_index in range(self._column.visibleRows):
                row_data = self._column.getRowCachedData(row_index)
                cursor.movePosition(QTextCursor.End)
                cursor.insertHtml(row_data.html)
                cursor.insertBlock()
                cursor.setBlockFormat(block_format)

            self.documentUpdated.emit()

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
                cursor.insertHtml(row_data.html)

                self.documentUpdated.emit()

    def removeRows(self, row_index, number_of_rows):
        if self._document is not None:
            for x in range(number_of_rows):
                block = self._document.findBlockByLineNumber(row_index)
                if block.isValid():
                    cursor = QTextCursor(block)
                    cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                    cursor.removeSelectedText()
                    if row_index == 0:
                        cursor.deleteChar()

            self.documentUpdated.emit()

    def insertRows(self, row_index, number_of_rows):
        if self._document is not None:
            for x in range(number_of_rows):
                if row_index < 0:
                    cursor = QTextCursor(self._document)
                    cursor.movePosition(QTextCursor.End)
                else:
                    block = self._document.findBlockByLineNumber(row_index)
                    cursor = QTextCursor(block)

                cursor.insertBlock()
                cursor.setBlockFormat(self._documentBlockFormat)

            self.documentUpdated.emit()

    def rectForCell(self, row_index, cell_index):
        self.generateDocument()

        try:
            index_data = self._column._cache[row_index].items[cell_index]
        except IndexError:
            return QRectF()

        if index_data is not None:
            block = self._document.findBlockByLineNumber(row_index)
            if block.isValid():
                block_rect = self._document.documentLayout().blockBoundingRect(block)
                line = block.layout().lineAt(0)
                x = line.cursorToX(index_data.firstCharIndex)[0]
                y = block_rect.y() + line.position().y()
                width = self._column._fontMetrics.width(index_data.text)
                return QRectF(x, y, width, self._column._fontMetrics.height())
        return QRectF()

    def rectForRow(self, row_index):
        self.generateDocument()

        block = self._document.findBlockByLineNumber(row_index)
        if block.isValid():
            block_rect = self._document.documentLayout().blockBoundingRect(block)
            return block_rect

        return QRectF()

    def cursorPositionInCell(self, row_index, cell_index, cursor_offset):
        try:
            index_data = self._column._cache[row_index].items[cell_index]
        except IndexError:
            return QPointF()

        if cursor_offset < 0 or cursor_offset >= len(index_data.text):
            return QPointF()

        block = self._document.findBlockByLineNumber(row_index)
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
                if index_data.firstCharIndex + len(index_data.text) > line_char_index:
                    return (row_index, column), line_char_index - index_data.firstCharIndex
        return (-1, -1), 0

    def cellFromPoint(self, point):
        return self._positionForPoint(point)[0]

    def cursorPositionFromPoint(self, point):
        return self._positionForPoint(point)[1]


# class TableDocumentBackend(ColumnDocumentBackend):
#     def __init__(self, column):
#         ColumnDocumentBackend.__init__(self, column)
#
#     def generateDocument(self):
#         if self._document is None:
#             self._document = self._column.createDocumentTemplate()
#
#             cursor = QTextCursor(self._document)
#
#             cursor.beginEditBlock()
#             try:
#                 self._table = cursor.insertTable(len(self._column._cache), self._column.model.columnCount(0))
#                 self._table.setFormat(self._tableFormat)
#                 for row_index in range(len(self._column._cache)):
#                     for column_index in range(self._table.columns()):
#                         cell = self._table.cellAt(row_index, column_index)
#                         cursor = cell.firstCursorPosition()
#                         try:
#                             cursor.insertHtml(self._column._cache[row_index].items[column_index].html)
#                         except IndexError:
#                             pass
#             finally:
#                 cursor.endEditBlock()
#
#             self.documentUpdated.emit()
#
#     @property
#     def _tableFormat(self):
#         fmt = QTextTableFormat()
#         fmt.setBorderStyle(QTextTableFormat.BorderStyle_None)
#         fmt.setBorder(0)
#         fmt.setCellPadding(0)
#         fmt.setCellSpacing(0)
#         return fmt
#
#     def updateRow(self, row_index, row_data):
#         if self._document is not None:
#             cursor = self._table.cellAt(row_index, 0).firstCursorPosition()
#             cursor.movePosition(QTextCursor.NextRow)
#             cursor.removeSelectedText()
#             cursor.beginEditBlock()  # we do not use undo/redo, but this thing increases perfomance, blocking updating
#                                      # layout until endEditBlock is called.
#             try:
#                 for column_index in range(self._table.columns()):
#                     cursor = self._table.cellAt(row_index, column_index).firstCursorPosition()
#                     cursor.insertHtml(row_data.items[column_index].html)
#             finally:
#                 cursor.endEditBlock()
#
#             self.documentUpdated.emit()
#
#     def removeRows(self, row_index, number_of_rows):
#         if self._document is not None:
#             self._table.removeRows(row_index, number_of_rows)
#             self.documentUpdated.emit()
#
#     def insertRows(self, row_index, number_of_rows):
#         if self._document is not None:
#             if row_index < 0:
#                 self._table.appendRows(number_of_rows)
#             else:
#                 self._table.insertRows(row_index, number_of_rows)
#
#             self.documentUpdated.emit()
#
#     def rectForCell(self, row_index, cell_index):
#         self.generateDocument()
#
#         cursor = self._table.cellAt(row_index, cell_index).firstCursorPosition()
#         if not cursor.isNull():
#             return self._document.documentLayout().blockBoundingRect(cursor.block())
#
#         return QRectF()
#
#     def cellFromPoint(self, point):
#         self.generateDocument()
#
#         for row_index in range(len(self._column._cache)):
#             for column_index in range(self._table.columns()):
#                 if self.rectForCell(row_index, column_index).contains(point):
#                     return row_index, column_index
#         return -1, -1


class Column(QObject):
    updateRequested = pyqtSignal()
    resizeRequested = pyqtSignal(QSizeF)
    headerResizeRequested = pyqtSignal()

    def __init__(self, model):
        QObject.__init__(self)
        self.sourceModel = model
        self.model = FrameProxyModel(model)
        self.model.dataChanged.connect(self._onDataChanged)
        self.model.modelReset.connect(self._invalidateCache)
        self.model.frameScrolled.connect(self._onFrameScrolled)
        self.model.frameResized.connect(self._onFrameResized)

        self._geom = QRectF()
        self._font = QFont()
        self._fontMetrics = QFontMetricsF(self._font)
        self._theme = DefaultTheme

        self._fullVisibleRows = 0
        self._visibleRows = 0
        self._firstVisibleRow = 0

        self._showHeader = False
        self._headerHeight = False
        self._headerData = []
        self._validator = self.sourceModel.createValidator()

        self._spaced = self.sourceModel.preferSpaced
        self._cache = None
        # if self.sourceModel.regular:
        #     self._documentBackend = TableDocumentBackend(self)
        # else:
        self._documentBackend = PlainTextDocumentBackend(self)
        self._documentDirty = True
        self._documentBackend.documentUpdated.connect(self._onDocumentUpdated)

    @property
    def geometry(self):
        return self._geom

    @geometry.setter
    def geometry(self, rect):
        self._geom = rect
        self._updateGeometry()
        # self.updateRequested.emit()  # even if frame was not changed, we should redraw widget

    @property
    def showHeader(self):
        return self._showHeader

    @showHeader.setter
    def showHeader(self, show):
        self._showHeader = show
        self._updateGeometry()
        # self.updateRequested.emit()

    def idealHeaderHeight(self):
        return self._fontMetrics.height() + VisualSpace / 2

    @property
    def headerHeight(self):
        return self.headerRect.height()

    @headerHeight.setter
    def headerHeight(self, height):
        self._headerHeight = height
        self.updateRequested.emit()

    @property
    def headerRect(self):
        if self.showHeader:
            return QRectF(QPointF(0, 0), QSizeF(self.geometry.width(), self._headerHeight))
        else:
            return QRectF()

    def getRectForHeaderItem(self, section_index):
        cell_rect = self.getRectForIndex(self.model.index(0, section_index))
        return QRectF(QPointF(cell_rect.x(), 0), QSizeF(cell_rect.width(), self.headerRect.height()))

    @property
    def firstVisibleRow(self):
        return self._firstVisibleRow

    def scrollToFirstRow(self, source_row_index):
        if self._firstVisibleRow != source_row_index:
            self._firstVisibleRow = source_row_index
            self.model.scrollFrame(self._firstVisibleRow)

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
        return self.model.index(0, 0)

    @property
    def lastVisibleIndex(self):
        return self.model.lastRowIndex(self._visibleRows - 1)

    @property
    def lastFullVisibleIndex(self):
        return self.model.lastRowIndex(self._fullVisibleRows - 1)

    @property
    def font(self):
        return self._font

    @font.setter
    def font(self, new_font):
        self._font = new_font
        self._fontMetrics = QFontMetricsF(new_font)
        if hasattr(self.sourceModel, 'renderFont'):  # well, this is hack until i invent better solution...
            self.sourceModel.renderFont = new_font
        self._documentBackend.clear()
        self.headerResizeRequested.emit()
        self._updateGeometry()
        self.updateRequested.emit()

    @property
    def editor(self):
        return self.sourceModel.editor

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
        return self.sourceModel.regular

    def getRowCachedData(self, visible_row_index):
        if self._cache is None:
            self._adjustCacheRows()
        if 0 <= visible_row_index < self._visibleRows:
            cached_row = self._cache[visible_row_index]
            if cached_row is None:
                self._updateCachedRow(visible_row_index)
            return self._cache[visible_row_index]

    def getIndexCachedData(self, index):
        index = self.model.fromSourceIndex(index)
        row_data = self.getRowCachedData(index.row)
        if row_data is not None and index.column < len(row_data.items):
            return row_data.items[index.column]

    def getRectForIndex(self, index):
        index = self.model.fromSourceIndex(index)
        rect = self._documentBackend.rectForCell(index.row, index.column)
        return rect.translated(self.documentOrigin)

    def cursorPositionInIndex(self, index, cursor_offset):
        index = self.model.fromSourceIndex(index)
        pos = self._documentBackend.cursorPositionInCell(index.row, index.column, cursor_offset)
        return QPointF(pos.x() + self.documentOrigin.x(), pos.y() + self.documentOrigin.y())

    def getPolygonsForRange(self, first_index, last_index):
        first_index = self.model.toSourceIndex(first_index)
        last_index = self.model.toSourceIndex(last_index)

        first_visible_source_index = self.model.toSourceIndex(self.firstVisibleIndex)
        last_visible_source_index = self.model.toSourceIndex(self.lastVisibleIndex)
        if not first_index or not last_index or (first_index > last_visible_source_index or
                                                         last_index < first_visible_source_index):
            return tuple()

        first_index = max(first_index, first_visible_source_index)
        last_index = min(last_index, last_visible_source_index)

        if first_index == last_index:
            return QPolygonF(self.getRectForIndex(first_index)),
        else:
            r1 = self.getRectForIndex(first_index)
            r2 = self.getRectForIndex(last_index)

            if first_index.row == last_index.row:
                return QPolygonF(QRectF(r1.topLeft(), r2.bottomRight())),
            elif first_index.row + 1 == last_index.row and r1.left() > r2.right():
                first_row_last_index = self.sourceModel.lastRowIndex(first_index.row)
                return (
                    QPolygonF(QRectF(r1.topLeft(), self.getRectForIndex(first_row_last_index).bottomRight())),
                    QPolygonF(QRectF(QPointF(VisualSpace, r2.top()), r2.bottomRight()))
                )
            else:
                range_polygon = QPolygonF()

                for row_index in range(first_index.row, last_index.row):
                    index = self.sourceModel.index(row_index, self.sourceModel.columnCount(row_index) - 1)
                    index_rect = self.getRectForIndex(index)
                    range_polygon.append(index_rect.topRight())
                    range_polygon.append(index_rect.bottomRight())

                range_polygon.append(r2.topRight())
                range_polygon.append(r2.bottomRight())
                range_polygon.append(self.getRectForIndex(self.sourceModel.index(last_index.row, 0)).bottomLeft())
                range_polygon.append(self.getRectForIndex(self.sourceModel.index(first_index.row, 0)).bottomLeft())
                range_polygon.append(r1.bottomLeft())
                range_polygon.append(r1.topLeft())

                return range_polygon,

    def indexFromPoint(self, point):
        point = QPointF(point.x() - self.documentOrigin.x(), point.y() - self.documentOrigin.y())
        row, column = self._documentBackend.cellFromPoint(point)
        return self.model.toSourceIndex(self.model.index(row, column))

    def cursorPositionFromPoint(self, point):
        point = QPointF(point.x() - self.documentOrigin.x(), point.y() - self.documentOrigin.y())
        return self._documentBackend.cursorPositionFromPoint(point)

    def paint(self, paint_data, is_leading):
        painter = paint_data.painter
        painter.save()

        painter.setPen(self._theme.textColor if is_leading else self._theme.inactiveTextColor)

        if settings.globalSettings()['hexwidget.alternating_rows']:
            for row_index in range(self._visibleRows):
                if (row_index + self._firstVisibleRow) % 2:
                    rect = self.rectForRow(row_index)
                    rect = QRectF(QPointF(0, rect.y() + self.documentOrigin.y()), QSizeF(self.geometry.width(), rect.height()))
                    painter.fillRect(rect, QBrush(self._theme.alternateRowColor))

        painter.translate(self.documentOrigin)

        # little trick to quickly change default text color for document without re-generating it
        paint_context = QAbstractTextDocumentLayout.PaintContext()
        paint_context.palette.setColor(QPalette.Text, self._theme.textColor if is_leading else self._theme.inactiveTextColor)
        paint_context.palette.setColor(QPalette.Window, QColor(0, 0, 0, 0))
        # standard QTextDocument.draw also sets clip rect here, but we already have one
        self._renderDocumentData()
        self._documentBackend.document.documentLayout().draw(painter, paint_context)

        painter.restore()

        self.paintHeader(paint_data, is_leading)

    def paintCaret(self, paint_data, is_leading, caret_position):
        painter = paint_data.painter
        if caret_position >= 0:
            caret_index = self.model.fromSourceIndex(self.sourceModel.indexFromPosition(caret_position))
            if caret_index and self.isIndexVisible(caret_index, False):
                caret_rect = self.getRectForIndex(caret_index)
                painter.setBrush(QBrush(self._theme.caretBackgroundColor))
                painter.setPen(self._theme.caretBorderColor)
                painter.drawRect(caret_rect)

    def paintSelection(self, paint_data, is_leading, selection):
        if selection is not None and len(selection) > 0:
            painter = paint_data.painter
            for sel_polygon in self.getPolygonsForRange(self.sourceModel.indexFromPosition(selection.start),
                                        self.sourceModel.indexFromPosition(selection.start + len(selection) -1)):
                painter.setBrush(self._theme.selectionBackgroundColor)
                painter.setPen(QPen(QBrush(self._theme.selectionBorderColor), 2.0))
                painter.drawPolygon(sel_polygon)

    class HeaderItemData(object):
        def __init__(self):
            self.text = ''

    def _updateHeaderData(self):
        self._headerData = []

        if not self.showHeader or not self.model.regular:
            return

        for column_index in range(self.model.columnCount(0)):
            cell_data = self.model.headerData(column_index, Qt.DisplayRole)
            if not isinstance(cell_data, str):
                cell_data = ''
            header_item_data = self.HeaderItemData()
            header_item_data.text = cell_data
            self._headerData.append(header_item_data)

    def paintHeader(self, paint_data, is_leading):
        # header can be painted only for regular columns
        if not self.showHeader:
            return

        painter = paint_data.painter
        painter.setPen(self._theme.headerTextColor if is_leading else self._theme.headerInactiveTextColor)

        painter.fillRect(self.headerRect, self._theme.headerBackgroundColor)

        for section_index in range(len(self._headerData)):
            rect = self.getRectForHeaderItem(section_index)
            painter.drawText(rect, Qt.AlignHCenter|Qt.TextSingleLine, self._headerData[section_index].text)

    @property
    def documentOrigin(self):
        return QPointF(VisualSpace, self.headerRect.height() + VisualSpace / 2)

    def _updateGeometry(self):
        real_height = max(self._geom.height() - self.documentOrigin.y(), 0)
        self._fullVisibleRows = int(real_height // self._fontMetrics.height())
        self._visibleRows = self._fullVisibleRows + bool(int(real_height) % int(self._fontMetrics.height()))
        self.model.resizeFrame(self._visibleRows)

    def _adjustCacheRows(self):
        """Adjusts row count in cache, but does not update any rows.
        """
        if self._cache is None:
            self._cache = [None] * self._visibleRows
        elif len(self._cache) > self._visibleRows:
            self._cache = self._cache[:self._visibleRows]
        elif len(self._cache) < self._visibleRows:
            self._cache += [None] * (self._visibleRows - len(self._cache))
        else:
            return

        self._documentDirty = True

    def _invalidateCache(self):
        """Invalidate entire cache"""
        self._cache = None
        self._documentDirty = True

    def _invalidateRow(self, row_index):
        """Invalidate only specified row in cache"""
        if self._cache is not None and 0 <= row_index < len(self._cache):
            self._cache[row_index] = None
            self._documentDirty = True

    def _renderDocumentData(self):
        """Ensures that document will contain actual data after calling this method"""
        if self._documentDirty:
            if self._cache is None:
                self._adjustCacheRows()

            for row_index in range(self._visibleRows):
                self._renderRowDataToDocument(row_index)

            self._updateHeaderData()

            self._documentDirty = False

    def _renderRowDataToDocument(self, row_index):
        """Updates cached row in document"""
        if 0 <= row_index < self._visibleRows:
            self._documentBackend.updateRow(row_index, self.getRowCachedData(row_index))

    def _onDocumentUpdated(self):
        ideal_width = self._documentBackend._document.idealWidth() + VisualSpace * 2
        if ideal_width != self._geom.width():
            self.resizeRequested.emit(QSizeF(ideal_width, self._geom.height()))

    def _updateCachedRow(self, row_index):
        assert(0 <= row_index < len(self._cache))

        row_data = RowData()
        row_data.html = '<div class="row">'
        column_count = self.model.columnCount(row_index)
        for column_index in range(column_count):
            index = self.model.toSourceIndex(self.model.index(row_index, column_index))
            index_data = IndexData(index)
            index_data.firstCharIndex = len(row_data.text)
            index_data.firstHtmlCharIndex = len(row_data.html)
            index_text = index_data.data()

            if index_text is not None:
                cell_classes = []
                if index.flags & ColumnModel.FlagModified:
                    cell_classes.append('cell-mod')

                prepared_text = html.escape(index_text)
                prepared_text = prepared_text.replace(' ', '&nbsp;')
                if cell_classes:
                    # unfortunately, HTML subset supported by Qt does not include multiclasses
                    for css_class in cell_classes:
                        index_html = '<span class="{0}">{1}</span>'.format(css_class, prepared_text)
                else:
                    index_html = '<span>{0}</span>'.format(prepared_text)

                row_data.html += index_html
                row_data.text += index_text
                index_data.html = index_html

            if self.spaced and column_index + 1 < column_count:
                row_data.text += ' '
                row_data.html += '<span> </span>'

            row_data.items.append(index_data)

        row_data.html += '</div>'
        self._cache[row_index] = row_data

    def _onFrameScrolled(self, new_first_row, old_first_row):
        if self._cache is None:
            return
        else:
            self._adjustCacheRows()

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
            self._documentDirty = True

            for row in range(scrolled_by):
                self._invalidateRow(valid_rows + row)
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
            self._documentDirty = True

            for row in range(scrolled_by):
                self._invalidateRow(row)
        else:
            # unfortunately... we should totally reset cache
            self._invalidateCache()
        self.updateRequested.emit()

    def _onFrameResized(self, new_frame_size, old_frame_size):
        if self._cache is None:
            return
        else:
            self._adjustCacheRows()

        if new_frame_size < old_frame_size:
            # just remove some rows...
            if self._documentBackend.generated:
                self._documentBackend.removeRows(new_frame_size, old_frame_size - new_frame_size)
        else:
            # add new rows and initialize them
            if self._documentBackend.generated:
                self._documentBackend.insertRows(-1, new_frame_size - old_frame_size)

        self.updateRequested.emit()

    def _onDataChanged(self, first_index, last_index):
        current_row = first_index.row
        while current_row <= last_index.row:
            self._invalidateRow(current_row)
            current_row += 1
        self.updateRequested.emit()

    def isIndexVisible(self, index, full_visible=False):
        if not index or index.model is not self.model and index.model is not self.sourceModel:
            return False

        index = self.model.fromSourceIndex(index)
        rows_count = self.fullVisibleRows if full_visible else self.visibleRows
        return bool(self.model.toSourceIndex(index) and index.row < rows_count)

    def createDocumentTemplate(self):
        document = QTextDocument()
        document.setDocumentMargin(0)
        document.setDefaultFont(self.font)
        document.setUndoRedoEnabled(False)

        document.setDefaultStyleSheet("""
            .cell-mod {{
                color: {mod_color};
            }}

            .highlight {{
                color: green;
            }}
        """.format(mod_color=self._theme.modifiedTextColor.name()))

        return document

    def removeIndex(self, index):
        pos = index.data(ColumnModel.EditorPositionRole)
        size = index.data(ColumnModel.DataSizeRole)
        if pos < 0 or size < 0:
            raise ValueError()
        self.editor.remove(pos, size)

    @property
    def validator(self):
        return self._validator

    def rectForRow(self, row_index):
        return self._documentBackend.rectForRow(row_index)


def _translate(x, dx, dy=0):
    if hasattr(x, 'translated'):
        return x.translated(QPointF(dx, dy))
    elif isinstance(x, (QPoint, QPointF)):
        return x + type(x)(dx, dy)
    else:
        raise TypeError('{0} is not translatable'.format(type(x)))


class HexWidget(QWidget):
    insertModeChanged = pyqtSignal(bool)
    canUndoChanged = pyqtSignal(bool)
    canRedoChanged = pyqtSignal(bool)
    isModifiedChanged = pyqtSignal(bool)
    hasSelectionChanged = pyqtSignal(bool)
    leadingColumnChanged = pyqtSignal(object)
    showHeaderChanged = pyqtSignal(bool)
    urlChanged = pyqtSignal(object)

    def __init__(self, parent, editor):
        from hex.floatscrollbar import LargeScrollBar

        QWidget.__init__(self, parent)

        globalSettings = settings.globalSettings()

        global DefaultTheme
        if DefaultTheme is None:
            DefaultTheme = Theme()
            DefaultTheme.load(globalSettings, 'hexwidget.default_theme')

        self.view = QWidget(self)
        self.view.installEventFilter(self)
        self.setFocusProxy(self.view)

        self.vScrollBar = LargeScrollBar(Qt.Vertical, self)
        self.vScrollBar.valueChangedLarge.connect(self._onVScroll)

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

        self._theme = DefaultTheme
        self._editor = editor
        self._columns = list()
        self._leadingColumn = None
        self._caretPosition = 0
        self._selections = []
        self._selectStartColumn = None
        self._selectStartIndex = None
        self._scrollTimer = None

        self._editMode = False
        self._cursorVisible = False
        self._cursorOffset = 0
        self._cursorTimer = None
        self._blockCursor = False
        self._insertMode = True

        self._showHeader = True
        self._dx = 0

        self._contextMenu = QMenu()
        self._actionCopy = self._contextMenu.addAction(utils.tr('Copy'))
        self._actionCopy.triggered.connect(self.copy)
        self._actionPaste = self._contextMenu.addAction(utils.tr('Paste'))
        self._actionPaste.triggered.connect(self.paste)
        self._contextMenu.addSeparator()
        self._actionSetup = self._contextMenu.addAction(utils.tr('Setup column...'))
        self._actionSetup.triggered.connect(self.setupActiveColumn)

        palette = QPalette(self.view.palette())
        palette.setColor(QPalette.Background, self._theme.backgroundColor)
        self.view.setPalette(palette)
        self.view.setAutoFillBackground(True)

        self.setFont(appsettings.getFontFromSetting(globalSettings['hexwidget.font']))

        from hex.hexcolumn import HexColumnModel
        from hex.charcolumn import CharColumnModel
        from hex.addresscolumn import AddressColumnModel

        hex_column = HexColumnModel(self.editor, IntegerCodec(IntegerCodec.Format8Bit, False),
                                         IntegerFormatter(16, padding=2))
        address_bar = AddressColumnModel(hex_column)
        self.appendColumn(address_bar)
        self.appendColumn(hex_column)
        self.appendColumn(CharColumnModel(self.editor, encodings.getCodec('UTF-16le'), self.font()))
        self.leadingColumn = self._columns[1]

        self.editor.canUndoChanged.connect(self.canUndoChanged, Qt.QueuedConnection)
        self.editor.canRedoChanged.connect(self.canRedoChanged, Qt.QueuedConnection)
        self.editor.isModifiedChanged.connect(self.isModifiedChanged, Qt.QueuedConnection)

        globalSettings.settingChanged.connect(self._onSettingChanged)

    def loadSettings(self, settings):
        self.showHeader = settings['hexwidget.show_header']

    def saveSettings(self, settings):
        settings['hexwidget.show_header'] = self.showHeader

    def _onSettingChanged(self, name, value):
        if name == 'hexwidget.show_header':
            self.showHeader = value
        elif name == 'hexwidget.alternating_rows':
            self.view.update()
        elif name == 'hexwidget.font':
            self.setFont(appsettings.getFontFromSetting(value))

    @property
    def editor(self):
        return self._editor

    def setFont(self, new_font):
        QWidget.setFont(self, new_font)
        for column in self._columns:
            column.font = self.font()
        self._updateScrollBars()

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
        if self.caretPosition != new_pos:
            self._caretPosition = new_pos
            self.view.update()

    @property
    def cursorOffset(self):
        return self._cursorOffset

    @cursorOffset.setter
    def cursorOffset(self, new_offset):
        if self._cursorOffset != new_offset:
            self._cursorOffset = new_offset
            self._updateCursorOffset()

    def caretIndex(self, column):
        return column.sourceModel.indexFromPosition(self.caretPosition) if column is not None else ModelIndex()

    def insertColumn(self, model, at_index=-1):
        if model is not None:
            column = Column(model)
            column.font = self.font()

            column.geometry = QRectF(QPointF(0, 0), QSizeF(200, self.view.height()))
            column.showHeader = self.showHeader
            self._columns.insert(at_index if at_index >= 0 else len(self._columns), column)

            self._adjustHeaderHeights()
            self._updateColumnsGeometry()

            column.updateRequested.connect(self._onColumnUpdateRequested)
            column.resizeRequested.connect(self._onColumnResizeRequested)
            column.headerResizeRequested.connect(self._adjustHeaderHeights)

            if self._leadingColumn is None:
                self._leadingColumn = column
            else:
                column.scrollToFirstRow(self._leadingColumn.firstVisibleRow)

            self.view.update()

    def appendColumn(self, model):
        self.insertColumn(model)

    def columnFromIndex(self, index):
        return utils.first(cd for cd in self._columns if cd.sourceModel is index.model or cd.model is index.model)

    def _columnToAbsolute(self, column, d):
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

        for column in self._columns:
            self._paintColumn(pd, column)

        self._paintCursor(pd)
        self._paintBorders(pd)

    def _paintColumn(self, pd, column):
        painter = pd.painter

        painter.setClipRect(self._absoluteToWidget(column.geometry))
        painter.translate(self._absoluteToWidget(column.geometry.topLeft()))

        column.paint(pd, self._leadingColumn is column)

        if not self._editMode or self._leadingColumn is not column:
            column.paintCaret(pd, self._leadingColumn is column, self._caretPosition)

        # paint selections
        for sel in self._selections:
            column.paintSelection(pd, self._leadingColumn is column, sel)

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
            painter.drawLine(QLineF(0, self.headerHeight, self.view.width(), self.headerHeight))


    def _wheel(self, event):
        if event.orientation() == Qt.Vertical:
            if event.modifiers() == Qt.NoModifier:
                self.scroll((-event.delta() // 120) * 3)
            elif event.modifiers() == Qt.ControlModifier:
                self.zoom(event.delta() // 120)
        event.accept()

    def scroll(self, row_delta):
        """Delta is number of rows to scroll by. Negative means scroll up, positive - down."""
        if row_delta and self._leadingColumn is not None:
            new_first_row = self.leadingColumn.firstVisibleRow + row_delta
            model_row_count = self._leadingColumn.sourceModel.rowCount()
            if new_first_row < 0:
                new_first_row = 0
            elif model_row_count >= 0 and new_first_row >= model_row_count:
                new_first_row = model_row_count - 1
            self.scrollToLeadingColumnRow(new_first_row)

    def scrollToLeadingColumnRow(self, first_row, correct=False):
        if first_row < 0:
            if correct:
                first_row = 0
            else:
                return
        elif self.leadingColumn.sourceModel.rowCount() >= 0:
            if first_row >= self.leadingColumn.sourceModel.rowCount():
                if correct:
                    first_row = self.leadingColumn.sourceModel.rowCount() - 1
                else:
                    return

        self.leadingColumn.scrollToFirstRow(first_row)
        self.syncColumnsFrames()
        self._updateScrollBars()
        self.update()

    def syncColumnsFrames(self, sync_row=0):
        for column in self._columns:
            self.syncColumnFrame(column, sync_row)

    def syncColumnFrame(self, column, sync_row=0):
        if self.leadingColumn is not None and column is not None and column is not self.leadingColumn:
            editor_position = self.leadingColumn.model.index(sync_row, 0).data(ColumnModel.EditorPositionRole)
            if editor_position is not None:
                # position frame of non-leading column so same data will be on same row
                sync_index = column.sourceModel.indexFromPosition(editor_position)
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
        self.setFont(appsettings.getFontFromSetting(settings.globalSettings()['hexwidget.font']))

    def isIndexVisible(self, index, full_visible=True):
        column = self.columnFromIndex(index)
        return bool(column is not None and column.isIndexVisible(index, full_visible))

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
            max_value = max(lc.sourceModel.realRowCount() - 1, lc.firstVisibleRow)
            self.vScrollBar.setRangeLarge(0, max_value)
            self.vScrollBar.setPageStepLarge(lc.visibleRows)
            # self.vScrollBar.setSingleStepLarge(1)
            self.vScrollBar.setValueLarge(lc.firstVisibleRow)
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
        model = lc.sourceModel
        return lc.firstVisibleRow > 0 or model.realRowCount() > lc.visibleRows or (0 < model.realRowCount() <= lc.firstVisibleRow)

    @property
    def _shouldShowHScroll(self):
        return self._dx > 0 or self._totalWidth > self.view.width()

    @property
    def _totalWidth(self):
        return sum(column.geometry.width() for column in self._columns)

    def _onVScroll(self, value):
        if self._leadingColumn is not None:
            if int(value) != self._leadingColumn.firstVisibleRow:
                self.scrollToLeadingColumnRow(int(value))

    def _onHScroll(self, value):
        self._dx = value
        self.view.update()

    def _onColumnUpdateRequested(self):
        self.view.update()

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

        self.view.update()

    _edit_keys = (Qt.Key_Backspace, Qt.Key_Delete)

    def _keyPress(self, event):
        method = None
        if event.key() == Qt.Key_Right:
            method = self.NavMethod_NextCell if not self._editMode else self.NavMethod_NextCharacter
        elif event.key() == Qt.Key_Left:
            method = self.NavMethod_PrevCell if not self._editMode else self.NavMethod_PrevCharacter
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
                method = self.NavMethod_EditorStart
            else:
                method = self.NavMethod_RowStart if not self._editMode else self.NavMethod_CellStart
        elif event.key() == Qt.Key_End:
            if event.modifiers() & Qt.ControlModifier:
                method = self.NavMethod_EditorEnd
            else:
                method = self.NavMethod_RowEnd if not self._editMode else self.NavMethod_CellEnd

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
            if not self._editMode:
                self.startEditMode()
        elif event.key() == Qt.Key_Delete:
            self.deleteSelected()
        elif event.key() == Qt.Key_Escape:
            if self._editMode:
                self.endEditMode()
        elif self._editMode and (event.text() or event.key() in self._edit_keys):
            self._inputEvent(event)
        elif event.key() == Qt.Key_Insert:
            self._insertMode = not self._insertMode
            self.insertModeChanged.emit(self._insertMode)

    def _inputEvent(self, event):
        # input text into active cell
        index = self.caretIndex(self._leadingColumn)
        cursor_offset = self._cursorOffset
        if index:
            original_text = index.data(Qt.EditRole)
            changed_text = None
            insert_new_cell = False

            if event.key() == Qt.Key_Backspace:
                if self._cursorOffset == 0:
                    # remove index from the left
                    index_to_remove = index.previous
                    if index_to_remove and not index_to_remove.virtual:
                        self._leadingColumn.removeIndex(index_to_remove)
                else:
                    changed_text = original_text[:cursor_offset-1] + original_text[cursor_offset:]
            elif event.text():
                if self._cursorOffset == 0 and self._insertMode:
                    # when in insert mode, pressing character key when cursor is at beginning of cell inserts new cell
                    original_text = self._leadingColumn.sourceModel.defaultIndexData(Qt.EditRole)
                    insert_new_cell = True

                if self._leadingColumn.regular:
                    # replace character at cursor offset
                    changed_text = original_text[:cursor_offset] + event.text() + original_text[cursor_offset+1:]
                else:
                    # insert character at cursor offset
                    changed_text = original_text[:cursor_offset] + event.text() + original_text[cursor_offset:]

            if changed_text is not None:
                validator = self._leadingColumn.validator
                if validator is not None and validator.validate(changed_text) != QValidator.Acceptable:
                    return

                if insert_new_cell:
                    self.editor.beginComplexAction()
                    try:
                        index = self._leadingColumn.sourceModel.insertIndex(index)
                        index.setData(changed_text)
                    finally:
                        self.editor.endComplexAction()
                else:
                    index.setData(changed_text)

            if changed_text:
                # advance cursor
                self._navigate(self.NavMethod_NextCharacter)
            elif event.key() == Qt.Key_Backspace:
                self._navigate(self.NavMethod_PrevCharacter)
                self.cursorOffset = 0

    (NavMethod_NextCell, NavMethod_PrevCell, NavMethod_RowStart, NavMethod_RowEnd, NavMethod_ScreenUp,
        NavMethod_ScreenDown, NavMethod_RowUp, NavMethod_RowDown, NavMethod_EditorStart, NavMethod_EditorEnd,
        NavMethod_NextCharacter, NavMethod_PrevCharacter, NavMethod_CellEnd, NavMethod_CellStart) = range(14)

    def _goNextCell(self):
        self._goCaretIndex(self.caretIndex(self._leadingColumn).next)

    def _goPrevCell(self):
        self._goCaretIndex(self.caretIndex(self._leadingColumn).previous)

    def _goRowStart(self):
        self._goCaretIndex(self._leadingColumn.sourceModel.index(self.caretIndex(self._leadingColumn).row, 0))

    def _goRowEnd(self):
        index = self.caretIndex(self._leadingColumn)
        self._goCaretIndex(self._leadingColumn.sourceModel.lastRowIndex(index.row))

    def _goScreenDown(self):
        self._goByRows(self._leadingColumn.fullVisibleRows - 1)

    def _goScreenUp(self):
        self._goByRows(-(self._leadingColumn.fullVisibleRows - 1))

    def _goRowUp(self):
        self._goByRows(-1)

    def _goRowDown(self):
        self._goByRows(1)

    def _goEditorStart(self):
        self._goCaretIndex(self._leadingColumn.sourceModel.index(0, 0))

    def _goEditorEnd(self):
        self._goCaretIndex(self._leadingColumn.sourceModel.lastRealIndex)

    def _goNextCharacter(self):
        caret_index = self.caretIndex(self._leadingColumn)

        new_caret_index = caret_index
        new_cursor_offset = self._cursorOffset + 1
        if new_cursor_offset >= len(caret_index.data()):
            new_caret_index = self.findNextEditableIndex(caret_index)
            new_cursor_offset = 0

        self._goCaretIndex(new_caret_index)
        self.cursorOffset = new_cursor_offset

    def _goPrevCharacter(self):
        caret_index = self.caretIndex(self._leadingColumn)

        new_caret_index = caret_index
        new_cursor_offset = self._cursorOffset - 1
        if new_cursor_offset < 0:
            new_caret_index = self.findPreviousEditableIndex(caret_index)
            new_cursor_offset = len(new_caret_index.data()) - 1 if new_caret_index else -1

        self._goCaretIndex(new_caret_index)
        self._cursorOffset = new_cursor_offset

    def _goCaretIndex(self, new_caret_index):
        if not new_caret_index:
            return

        caret_index = self.caretIndex(self._leadingColumn)

        # make caret position full-visible (even if caret is not moved)
        if not self.isIndexVisible(new_caret_index, True):
            if caret_index.row < new_caret_index.row:
                new_first_row = new_caret_index.row - self.leadingColumn.fullVisibleRows + 1
            elif caret_index.row > new_caret_index.row:
                new_first_row = new_caret_index.row
            else:
                new_first_row = new_caret_index.row - int(self.leadingColumn.fullVisibleRows // 2) + 1
            self.scrollToLeadingColumnRow(new_first_row, correct=True)

        if new_caret_index != caret_index:
            self.caretPosition = new_caret_index.data(ColumnModel.EditorPositionRole)

        if self._editMode:
            self._updateCursorOffset()

    def _goByRows(self, row_count):
        caret_index = self.caretIndex(self._leadingColumn)
        if not caret_index:
            return

        data_model = self._leadingColumn.sourceModel

        new_row = caret_index.row + row_count
        if new_row < 0:
            new_row = 0
        elif data_model.rowCount() >= 0 and new_row >= data_model.rowCount():
            new_row = data_model.rowCount() - 1

        new_caret_index = None
        while not new_caret_index and data_model.hasRow(new_row):
            new_caret_index = data_model.index(new_row, caret_index.column)
            if not new_caret_index:
                new_caret_index = data_model.lastRowIndex(new_row)
            new_row += 1 if row_count > 0 else -1

        self._goCaretIndex(new_caret_index)

    def _goCellStart(self):
        self.cursorOffset = 0

    def _goCellEnd(self):
        index_text = self.caretIndex(self._leadingColumn).data()
        if index_text:
            self.cursorOffset = len(index_text) - 1

    navigate_callbacks = {
        NavMethod_NextCell: _goNextCell,
        NavMethod_PrevCell: _goPrevCell,
        NavMethod_RowStart: _goRowStart,
        NavMethod_RowEnd: _goRowEnd,
        NavMethod_ScreenDown: _goScreenDown,
        NavMethod_ScreenUp: _goScreenUp,
        NavMethod_RowUp: _goRowUp,
        NavMethod_RowDown: _goRowDown,
        NavMethod_EditorStart: _goEditorStart,
        NavMethod_EditorEnd: _goEditorEnd,
        NavMethod_NextCharacter: _goNextCharacter,
        NavMethod_PrevCharacter: _goPrevCharacter,
        NavMethod_CellEnd: _goCellEnd,
        NavMethod_CellStart: _goCellStart
    }

    def _navigate(self, method, make_selection=False):
        old_index = self.caretIndex(self._leadingColumn)
        self.navigate_callbacks[method](self)
        if make_selection and method not in (self.NavMethod_NextCharacter, self.NavMethod_PrevCharacter):
            new_index = self.caretIndex(self._leadingColumn)
            if old_index:
                # we will not select virtual indexes, but keep selection starting point for them
                if not old_index.virtual and not new_index.virtual:
                    # if we do not have any selection, create new one
                    if not self._selectStartIndex:
                        self._selectStartIndex = old_index
                        self._selectStartColumn = self.leadingColumn

                    # and create selection between stored position and current caret position
                    sel = self.selectionBetweenIndexes(new_index, self._selectStartIndex)
                    self.selections = [sel]
            else:
                self._selectStartIndex = None
                self._selectStartColumn = None

    def selectionBetweenIndexes(self, first, second):
        if not first or not second:
            return Selection()

        first_index = min(first, second)
        last_index = max(first, second)

        sel_start = first_index.data(ColumnModel.EditorPositionRole)
        sel_end = last_index.data(ColumnModel.EditorPositionRole) + last_index.data(ColumnModel.DataSizeRole)
        if sel_end > len(self.editor) and len(self.editor):
            sel_end = len(self.editor)

        return Selection(sel_start, sel_end - sel_start)

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
                if self._editMode:
                    self.endEditMode()
                self.leadingColumn = self._columns[column_index]

    def _mousePress(self, event):
        if event.button() in (Qt.LeftButton, Qt.RightButton):
            mouse_pos = self._widgetToAbsolute(event.posF())
            column = self.columnFromPoint(mouse_pos)
            if column is not None:
                if column is not self.leadingColumn:
                    self.leadingColumn = column

                pos = self._absoluteToColumn(column, mouse_pos)
                activated_index = column.model.toSourceIndex(column.indexFromPoint(pos))
                if activated_index:
                    if self._editMode and activated_index == self.caretIndex(column):
                        # move cursor position to nearest character
                        self.cursorOffset = max(column.cursorPositionFromPoint(self._absoluteToColumn(column, mouse_pos)), 0)
                    else:
                        self.endEditMode()
                        self.caretPosition = activated_index.data(ColumnModel.EditorPositionRole)

                        if not activated_index.virtual and event.button() == Qt.LeftButton:
                            self._selectStartIndex = activated_index
                            self._selectStartColumn = column
                            self._mousePressPoint = mouse_pos

    def _mouseRelease(self, event):
        self._selectStartIndex = None
        self._selectStartColumn = None
        self._stopScrollTimer()

    def _mouseMove(self, event):
        if self._selectStartIndex:
            mouse_pos = self._widgetToAbsolute(event.posF())

            column = self.columnFromPoint(mouse_pos)
            if column is not None:
                hover_index = column.indexFromPoint(self._absoluteToColumn(column, mouse_pos))
                if hover_index and column.sourceModel.rowCount() < 0 and hover_index > column.sourceModel.lastRealIndex:
                    hover_index = column.sourceModel.lastRealIndex

                if hover_index:
                    selections = None
                    if hover_index == self.caretIndex(column):
                        index_rect = self._columnToAbsolute(column, column.getRectForIndex(hover_index))
                        hit_rect = QRectF(QPointF(), QSizeF(index_rect.width() // 2, index_rect.height() // 2))
                        hit_rect.moveCenter(self._mousePressPoint)
                        if hit_rect.contains(mouse_pos):
                            selections = []

                    if selections is None:
                        selections = [self.selectionBetweenIndexes(self._selectStartIndex, hover_index)]

                    if selections != self._selections:
                        self.selections = selections
                        self.view.update()

            self._stopScrollTimer()

            overpos = 0
            if mouse_pos.y() < 0:
                overpos = mouse_pos.y()
            elif mouse_pos.y() > self.view.height():
                overpos = mouse_pos.y() - self.view.height()
            overpos = min(overpos, 100)
            if overpos:
                self._startScrollTimer(math.ceil(overpos / 20))

    def _mouseDoubleClick(self, event):
        if not self._editMode:
            mouse_pos = self._widgetToAbsolute(event.posF())
            column = self.columnFromPoint(mouse_pos)
            if column is not None:
                index = column.indexFromPoint(self._absoluteToColumn(column, mouse_pos))
                if index.flags & ColumnModel.FlagEditable:
                    self.startEditMode()
                    offset = column.cursorPositionFromPoint(self._absoluteToColumn(column, mouse_pos))
                    self.cursorOffset = max(offset, 0)

    def _startScrollTimer(self, increment):
        self._stopScrollTimer()
        self._scrollTimer = QTimer()
        self._scrollTimer.timeout.connect(lambda: self.scroll(increment))
        self._scrollTimer.start(200)
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
            dlg = columnproviders.ConfigureColumnDialog(self, self, self._leadingColumn.sourceModel)
            dlg.exec_()

    _eventHandlers = {
        QEvent.Paint: _paint,
        QEvent.Wheel: _wheel,
        QEvent.Resize: _resize,
        QEvent.KeyPress: _keyPress,
        QEvent.MouseButtonPress: _mousePress,
        QEvent.MouseButtonRelease: _mouseRelease,
        QEvent.MouseMove: _mouseMove,
        QEvent.MouseButtonDblClick: _mouseDoubleClick,
        QEvent.ContextMenu: _contextMenu
    }

    def eventFilter(self, obj, event):
        if obj is self.view:
            handler = self._eventHandlers.get(event.type())
            if handler is not None:
                return bool(handler(self, event))
        return False

    @property
    def selections(self):
        return self._selections

    @selections.setter
    def selections(self, new_selections):
        if self._selections != new_selections:
            old_has_selection = self.hasSelection
            self._selections = new_selections
            if old_has_selection != self.hasSelection:
                self.hasSelectionChanged.emit(self.hasSelection)
            self.view.update()

    @property
    def editMode(self):
        return self._editMode

    def startEditMode(self):
        if not self._editMode and not self._editor.readOnly:
            caret_index = self._leadingColumn.sourceModel.indexFromPosition(self._caretPosition)
            # check if current index is editable
            if caret_index and caret_index.flags & ColumnModel.FlagEditable:
                self._editMode = True
                self._cursorVisible = True
                self._cursorOffset = 0
                self._cursorTimer = QTimer()
                self._cursorTimer.timeout.connect(self._toggleCursor)
                self._cursorTimer.start(QApplication.cursorFlashTime())
                self.view.update()

    def endEditMode(self):
        if self._editMode:
            self._editMode = False
            self._cursorTimer.stop()
            self._cursorTimer.deleteLater()
            self._cursorTimer = None
            self.view.update()

    def clearSelection(self):
        self.selections = []

    def selectAll(self):
        if self.editor is not None:
            self.selections = [Selection(0, len(self._editor))]

    def copy(self):
        if len(self._selections) == 1:
            from hex.clipboard import Clipboard

            clb = Clipboard()
            clb.copy(self.editor, self._selections[0].start, self._selections[0].length)

    def paste(self):
        from hex.clipboard import Clipboard

        clb = Clipboard()
        span = clb.spanFromData(self.editor)
        if span is not None:
            try:
                self.editor.insertSpan(self.caretPosition, span)
            except IOError:
                pass

    def undo(self):
        try:
            self.editor.undo()
        except IOError:
            pass

    def canUndo(self):
        return self.editor.canUndo()

    def canRedo(self):
        return self.editor.canRedo()

    def redo(self, branch=None):
        try:
            self.editor.redo(branch)
        except IOError:
            pass

    def deleteSelected(self):
        """Deletes all bytes that are selected"""
        if not self._editor.readOnly and not self._editor.fixedSize:
            self._editor.beginComplexAction()
            try:
                for selection in self._selections:
                    self._editor.remove(selection.start, selection.length)
            finally:
                self._editor.endComplexAction()

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
        if self._editMode and self._cursorVisible and self.isIndexVisible(self.caretIndex(self._leadingColumn)):
            cursor_pos = self._absoluteToWidget(self._cursorPosition())
            font_metrics = QFontMetricsF(self.font())
            line_height = font_metrics.height()
            if self._blockCursor:
                try:
                    char_under_cursor = self.caretIndex(self._leadingColumn).data()[self._cursorOffset]
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
        if self._editMode and self._cursorVisible and self.isIndexVisible(caret_index):
            return self._columnToAbsolute(self._leadingColumn,
                                          self._leadingColumn.cursorPositionInIndex(caret_index, self._cursorOffset))
        return QPointF()

    def _toggleCursor(self):
        if self._editMode:
            self._cursorVisible = not self._cursorVisible
        else:
            self._cursorVisible = True
        self.view.update()

    def findNextEditableIndex(self, from_index):
        cindex = from_index.next
        while cindex and not cindex.flags & ColumnModel.FlagEditable:
            cindex = cindex.next
        return cindex

    def findPreviousEditableIndex(self, from_index):
        cindex = from_index.previous
        while cindex and not cindex.flags & ColumnModel.FlagEditable:
            cindex = cindex.previous
        return cindex

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
            self.editor.remove(selection.start, selection.length)
        self.selections = []

    def fillSelected(self, pattern):
        for selection in self._selections:
            self.editor.writeSpan(selection.start, FillSpan(self.editor, pattern, selection.length))
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
            address_column_model.linkedModel = self._leadingColumn.sourceModel
            self.insertColumn(address_column_model, column_index)

    @property
    def hasSelection(self):
        return bool(self._selections)

    @property
    def readOnly(self):
        return self.editor.readOnly if self.editor is not None else True

    @property
    def isModified(self):
        return self.editor.isModified if self.editor is not None else False

    def save(self, device=None, switch_to_device=False):
        if self.editor is not None:
            self.editor.save(device, switch_to_device)
            self.reset()

    def reset(self):
        for column in self._columns:
            column.sourceModel.reset()

    @property
    def url(self):
        return self.editor.url if self.editor is not None else QUrl()


class Selection(object):
    def __init__(self, start=0, length=0):
        self.start = start
        self.length = length

    def __len__(self):
        return self.length

    def __eq__(self, other):
        if not isinstance(other, Selection):
            return NotImplemented
        return self.start == other.start and self.length == other.length

    def __ne__(self, other):
        if not isinstance(other, Selection):
            return NotImplemented
        return not self.__eq__(other)


def _check_square_hit(square_center, square_size, point):
    square_size = square_size / 2
    if abs(square_center.x() - point.x()) <= square_size and abs(square_center.y() - point.y()) <= square_size:
        return True
    return False
