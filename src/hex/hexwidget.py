from PyQt4.QtCore import pyqtSignal, QObject, Qt, QPointF, QRectF, QPoint, QRect, QSizeF, QEvent, QTimer, QLineF, QSize
from PyQt4.QtGui import QColor, QFont, QFontMetricsF, QPolygonF, QWidget, QScrollBar, QVBoxLayout, QHBoxLayout, \
                        QPainter, QBrush, QPalette, QPen, QApplication, QRegion, QLineEdit, QValidator, \
                        QTextEdit, QTextOption, QSizePolicy, QStyle, QStyleOptionFrameV2, QTextCursor
from hex.utils import first
import math
from hex.valuecodecs import IntegerCodec
from hex.formatters import IntegerFormatter
from hex.editor import DataSpan
from hex.proxystyle import ProxyStyle


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
    modelReset = pyqtSignal()

    def __init__(self, editor=None):
        QObject.__init__(self)

        if editor is not None:
            with editor.lock:
                self.__editor = editor
                self.__editor.dataChanged.connect(self.onEditorDataChanged)
                self.__editor.resized.connect(self.onEditorDataResized)
        else:
            self.__editor = None

    @property
    def editor(self):
        return self.__editor

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
        """Return True if this model is regular. Regular models have same number of columns in each row"""
        return False

    def createEditWidget(self, parent, index, style_options):
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


class HexColumnModel(ColumnModel):
    """Standart column for hex-editors. Displays data as numbers. This model is regular (has equal number of
    columns in each row, except last one) and infinite (supports virtual indexes).
    """

    def __init__(self, editor, valuecodec, formatter, columns_on_row=16):
        ColumnModel.__init__(self, editor)
        self.valuecodec = valuecodec
        self.formatter = formatter
        self._rowCount = 0
        self._bytesOnRow = columns_on_row * self.valuecodec.dataSize
        self._columnsOnRow = columns_on_row
        self._updateRowCount()

    def rowCount(self):
        return -1

    def columnCount(self, row):
        return self._columnsOnRow

    def realRowCount(self):
        return self._rowCount

    def realColumnCount(self, row):
        if row + 1 >= self._rowCount:
            return (len(self.editor) % self.bytesOnRow) // self.valuecodec.dataSize
        elif row >= self._rowCount:
            return 0
        return self._columnsOnRow

    def indexFromPosition(self, editor_position):
        return ModelIndex(int(editor_position // self.bytesOnRow),
                          int(editor_position % self.bytesOnRow) // self.valuecodec.dataSize,
                          self)

    def indexData(self, index, role=Qt.DisplayRole):
        if not index or self.editor is None:
            return None
        editor_position = self.bytesOnRow * index.row + self.valuecodec.dataSize * index.column

        if role == Qt.DisplayRole or role == Qt.EditRole:
            if editor_position >= len(self.editor):
                return '..' #TODO: replace with '.' * self.cellTextSize
            else:
                editor_data = self.editor.read(editor_position, self.valuecodec.dataSize)
                return self.formatter.format(self.valuecodec.decode(editor_data))
        elif role == self.EditorDataRole:
            if editor_position >= len(self.editor):
                return bytes()
            else:
                return self.editor.read(editor_position, self.valuecodec.dataSize)
        elif role == self.DataSizeRole:
            return self.valuecodec.dataSize
        elif role == self.EditorPositionRole:
            return editor_position
        return None

    def setIndexData(self, index, value, role):
        if index and index.model is self:
            if role == self.EditorDataRole:
                position = self.indexData(index, ColumnModel.EditorPositionRole)
                if position is not None and position >= 0:
                    self.editor.writeSpan(position, DataSpan(self.editor, value))
                    return True
        return False

    def indexFlags(self, index):
        flags = ColumnModel.FlagEditable
        if index.row >= self._rowCount or (index.row == self._rowCount - 1 and index > self.lastRealIndex):
            flags |= ColumnModel.FlagVirtual
        if self.editor is not None and self.editor.isRangeModified(index.data(self.EditorPositionRole),
                                                                   index.data(self.DataSizeRole)):
            flags |= ColumnModel.FlagModified
        return flags

    @property
    def bytesOnRow(self):
        return self._bytesOnRow

    def onEditorDataChanged(self, start, length):
        length = length if length >= 0 else len(self.editor) - start
        self.dataChanged.emit(self.indexFromPosition(start), self.indexFromPosition(start + length - 1))

    def onEditorDataResized(self, new_size):
        self._updateRowCount()

    @property
    def preferSpaced(self):
        return True

    def _updateRowCount(self):
        self._rowCount = len(self.editor) // self.bytesOnRow + bool(len(self.editor) % self.bytesOnRow)

    def createEditWidget(self, parent, index, style_options):
        return HexColumnEditWidget(parent, index, style_options)


class AddressColumnModel(ColumnModel):
    def __init__(self, linked_model, formatter=None):
        ColumnModel.__init__(self, linked_model.editor)
        self._linkedModel = linked_model
        self._formatter = formatter or IntegerFormatter()
        self._baseAddress = 0
        self._updatePadding()

    @property
    def linkedModel(self):
        return self._linkedModel

    @linkedModel.setter
    def linkedModel(self, model):
        if self._linkedModel is not model:
            self._linkedModel = model
            self.modelReset.emit()

    @property
    def baseAddress(self):
        return self._baseAddress

    @baseAddress.setter
    def baseAddress(self, new_base):
        if self._baseAddress != new_base:
            self._baseAddress = new_base
            self.modelReset.emit()

    def rowCount(self):
        if self._linkedModel is not None:
            return self._linkedModel.rowCount()
        return 0

    def columnCount(self, row):
        return 1 if self._linkedModel is not None and self._linkedModel.hasRow(row) else 0

    def realRowCount(self):
        if self._linkedModel is not None:
            return self._linkedModel.realRowCount()
        return 0

    def realColumnCount(self, row):
        if self._linkedModel is not None:
            return int(bool(self._linkedModel.realColumnCount(row)))
        return 0

    def indexData(self, index, role=Qt.DisplayRole):
        if self._linkedModel is not None:
            model_index = self._linkedModel.index(index.row, 0)
            if role == Qt.DisplayRole and model_index:
                raw = model_index.data(self.EditorPositionRole) - self._baseAddress
                return self._formatter.format(raw) if self._formatter is not None else raw
            elif role == self.EditorPositionRole:
                return model_index.data(self.EditorPositionRole)
            elif role == self.DataSizeRole:
                return sum(index.data(self.DataSizeRole) for index in index_range(
                    model_index, self._linkedModel.lastRowIndex(index.row), include_last=True
                ))
        return None

    def indexFromPosition(self, position):
        if self._linkedModel is not None:
            model_index = self._linkedModel.indexFromPosition(position)
            return self.index(model_index.row, 0) if model_index else ModelIndex()
        return self._linkedModelone

    def indexFlags(self, index):
        if self._linkedModel is not None:
            model_index = self._linkedModel.index(index.row, 0)
            if model_index and model_index.flags & ColumnModel.FlagVirtual:
                return ColumnModel.FlagVirtual
        return 0

    def _maxLengthForSize(self, size):
        """Calculate maximal length of address text for given editor size"""
        sign1 = self._baseAddress > 0
        sign2 = self._baseAddress < len(self._linkedModel.editor)
        max_raw = max(abs(0 - self._baseAddress) + sign1,
                      abs(len(self._linkedModel.editor) - self._baseAddress) + sign2)
        return len(self._formatter.format(max_raw))

    def _updatePadding(self):
        if self._formatter is None:
            self._formatter = IntegerFormatter()
        self._formatter.padding = self._maxLengthForSize(len(self.editor))

    def onEditorDataResized(self, new_size):
        self._updatePadding()


class FrameProxyModel(ColumnModel):
    """This proxy model displays only number of rows starting after given first row. Proxy model does not check
    if there are indexes on these rows."""

    def __init__(self, source_model):
        ColumnModel.__init__(self, None)
        self.__firstRow = 0
        self.__rowCount = 0
        self.sourceModel = source_model or EmptyColumnModel()
        self.sourceModel.dataChanged.connect(self.__onDataChanged)
        self.sourceModel.modelReset.connect(self.modelReset)

    def setFrame(self, first_row, row_count):
        self.__firstRow = first_row
        self.__rowCount = row_count
        self.modelReset.emit()

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

    @property
    def regular(self):
        return self.sourceModel.regular


DefaultFont = QFont('Ubuntu Mono', 13)
VisualSpace = 10

# default color theme
BackgroundColor = QColor(250, 250, 245)
TextColor = QColor(Qt.black)
BorderColor = QColor(Qt.black)
InactiveTextColor = QColor(Qt.darkGray)
CaretBackgroundColor = QColor(150, 250, 160, 100)
CaretBorderColor = QColor(0, 0, 0, 255)
SelectionBackgroundColor = QColor(220, 250, 245, 100)
SelectionBorderColor = QColor(20, 205, 195)
# EditCaretBackgroundColor = QColor(0, 0, 0, 150)
# EditCaretBorderColor = EditCaretBackgroundColor
EditCaretTextColor = QColor(Qt.white)
ModifiedTextColor = QColor(Qt.red)


class RowData(object):
    def __init__(self):
        self.text = ''
        self.items = []


class IndexData(object):
    def __init__(self, index):
        self._text = None
        self.index = index
        self.firstCharIndex = 0
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


class Column(QObject):
    updateRequested = pyqtSignal()
    resizeRequested = pyqtSignal(QSizeF)

    def __init__(self, model):
        QObject.__init__(self)
        self.sourceModel = model
        self.model = FrameProxyModel(model)
        self.model.dataChanged.connect(self._updateCache)
        self.model.modelReset.connect(self._updateCache)

        self._geom = QRectF()
        self._font = DefaultFont
        self._fontMetrics = QFontMetricsF(self._font)

        self._fullVisibleRows = 0
        self._visibleRows = 0
        self._firstVisibleRow = 0

        self._spaced = self.sourceModel.preferSpaced
        self._cache = []

    @property
    def geometry(self):
        return self._geom

    @geometry.setter
    def geometry(self, rect):
        self._geom = rect
        self._updateGeometry()
        self.updateRequested.emit()  # even if frame not changed, we should redraw widget

    @property
    def firstVisibleRow(self):
        return self._firstVisibleRow

    def scrollToFirstRow(self, source_row_index):
        if self._firstVisibleRow != source_row_index:
            self._firstVisibleRow = source_row_index
            self.model.setFrame(self._firstVisibleRow, self._visibleRows)

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
        self._updateGeometry()

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
            self._updateCache()

    def getRowCachedData(self, visible_row_index):
        return self._cache[visible_row_index] if 0 <= visible_row_index < len(self._cache) else None

    def getIndexCachedData(self, index):
        index = self.model.fromSourceIndex(index)
        row_data = self.getRowCachedData(index.row)
        if row_data is not None and index.column < len(row_data.items):
            return row_data.items[index.column]
        return None

    def getRectForIndex(self, index):
        index = self.model.fromSourceIndex(index)
        index_data = self.getIndexCachedData(index)
        if index_data is not None:
            x = self._fontMetrics.width(self.getRowCachedData(index.row).text[:index_data.firstCharIndex]) + VisualSpace
            y = self._fontMetrics.height() * index.row
            width = self._fontMetrics.width(index_data.text)
            return QRectF(x, y, width, self._fontMetrics.height())
        return QRectF()

    def getRectForChar(self, index, char_offset):
        index_rect = self.getRectForIndex(index)
        if index_rect.width() and index_rect.height() and char_offset < len(index.data()):
            char_x = self._fontMetrics.width(index.data()[:char_offset])
            index_rect.setLeft(index_rect.left() + char_x)
            index_rect.setWidth(self._fontMetrics.width(index.data()[char_offset]))
            return index_rect
        return QRectF()

    def getRectForRow(self, visible_row_index):
        row_data = self.getRowCachedData(visible_row_index)
        if row_data is not None:
            last_index_rect = self.getRectForIndex(self.model.lastRowIndex(visible_row_index))
            return QRectF(QPointF(VisualSpace, self._fontMetrics.height() * visible_row_index),
                          last_index_rect.bottomRight())
        return QRectF()

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
        """Point should be in column relative coordinates"""
        row_index = int(point.y() / self._fontMetrics.height())
        if 0 <= row_index < self._visibleRows:
            for column in range(self.model.columnCount(row_index)):
                index_rect = self.getRectForIndex(self.model.index(row_index, column))
                if point.x() <= index_rect.right():
                    return self.model.toSourceIndex(self.model.index(row_index, column))
        return ModelIndex()

    def paint(self, paint_data, is_leading):
        painter = paint_data.painter
        painter.save()

        first_row = int(paint_data.dirtyRect.top() / self._fontMetrics.height())
        last_row = int(math.ceil(paint_data.dirtyRect.bottom() / self._fontMetrics.height()))

        for row_index in range(first_row, last_row):
            self.paintRow(paint_data, is_leading, row_index)

        painter.restore()

    def paintRow(self, paint_data, is_leading, row_index):
        if not (0 <= row_index < self._visibleRows):
            return

        painter = paint_data.painter
        painter.setFont(self.font)
        default_color = TextColor if is_leading else InactiveTextColor
        row_data = self.getRowCachedData(row_index)

        if not row_data.items:
            return

        # determine number of items that should be painted in one color
        cur_color = default_color
        cur_text = ''
        first_item = None
        item_index = 0

        # enumerate items until end of until we get item with another color
        for item in row_data.items:
            item_color = item.color or default_color
            if item_color != cur_color:
                # if this item has different color, draw previous ones (if we have text)
                if cur_text:
                    if item_index is not None:
                        painter.setPen(cur_color)
                        rect = QRectF(self.getRectForIndex(first_item.index).topLeft(),
                                      self.getRectForIndex(item.index.previous).bottomRight())
                        painter.drawText(rect, Qt.AlignVCenter, cur_text)
                cur_text = ''
                first_item = item
                cur_color = item_color

            next_item_char = len(row_data.text) if item_index + 1 >= len(row_data.items) else row_data.items[item_index + 1].firstCharIndex
            cur_text += row_data.text[item.firstCharIndex:next_item_char]
            item_index += 1

        # if we reached end, we should draw items that are left
        if cur_text:
            if first_item is None:
                first_item = row_data.items[0]
            painter.setPen(cur_color)
            rect = QRectF(self.getRectForIndex(first_item.index).topLeft(),
                          self.getRectForIndex(self.model.lastRowIndex(row_index)).bottomRight())
            painter.drawText(rect, Qt.AlignVCenter, cur_text)

    def paintCaret(self, paint_data, is_leading, caret_position):
        painter = paint_data.painter
        if caret_position >= 0:
            caret_index = self.model.fromSourceIndex(self.sourceModel.indexFromPosition(caret_position))
            if caret_index and self.isIndexVisible(caret_index, False):
                caret_rect = self.getRectForIndex(caret_index)
                painter.setBrush(QBrush(CaretBackgroundColor))
                painter.setPen(CaretBorderColor)
                painter.drawRect(caret_rect)

    def paintSelection(self, paint_data, is_leading, selection):
        if selection is not None and len(selection) > 0:
            painter = paint_data.painter
            for sel_polygon in self.getPolygonsForRange(self.sourceModel.indexFromPosition(selection.start),
                                        self.sourceModel.indexFromPosition(selection.start + len(selection) -1)):
                painter.setBrush(SelectionBackgroundColor)
                painter.setPen(QPen(QBrush(SelectionBorderColor), 2.0))
                painter.drawPolygon(sel_polygon)

    def _updateGeometry(self):
        self._fullVisibleRows = int(self._geom.height() // self._fontMetrics.height())
        self._visibleRows = self._fullVisibleRows + bool(int(self._geom.height()) % int(self._fontMetrics.height()))
        self.model.setFrame(self._firstVisibleRow, self._visibleRows)
        self._updateCache()
        self.updateRequested.emit()

    def _updateCache(self):
        old_cache = self._cache
        self._cache = []

        max_row_width = 0
        for row_index in range(self.visibleRows):
            row_data = RowData()
            column_count = self.model.columnCount(row_index)
            for column_index in range(column_count):
                index = self.model.index(row_index, column_index)
                index_data = IndexData(index)
                index_data.firstCharIndex = len(row_data.text)

                index_text = index_data.data()

                if index_text is not None:
                    row_data.text += index_text

                    if self.spaced and column_index != column_count - 1:
                        row_data.text += ' '

                    if index.flags & ColumnModel.FlagModified:
                        index_data.color = ModifiedTextColor

                row_data.items.append(index_data)

            row_width = self._fontMetrics.width(row_data.text) + VisualSpace * 2
            if row_width > max_row_width:
                max_row_width = row_width

            self._cache.append(row_data)

        if max_row_width != self._geom.width():
            self.resizeRequested.emit(QSizeF(max_row_width, self._geom.height()))

        self.updateRequested.emit()

    def isIndexVisible(self, index, full_visible=False):
        if not index or index.model is not self.model and index.model is not self.sourceModel:
            return False

        index = self.model.fromSourceIndex(index)
        rows_count = self.fullVisibleRows if full_visible else self.visibleRows
        return bool(self.model.toSourceIndex(index) and index.row < rows_count)

    def createEditWidget(self, parent, index, widget_options):
        return self.sourceModel.createEditWidget(parent, self.model.toSourceIndex(index), widget_options)


def _translate(x, dx, dy=0):
    if hasattr(x, 'translated'):
        return x.translated(QPointF(dx, dy))
    elif isinstance(x, (QPoint, QPointF)):
        return x + type(x)(dx, dy)
    else:
        raise TypeError('{0} is not translatable'.format(type(x)))


class HexWidget(QWidget):
    def __init__(self, parent, editor):
        from hex.floatscrollbar import LargeScrollBar

        QWidget.__init__(self, parent)

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

        self._editor = editor
        self._columns = list()
        self._leadingColumn = None
        self._caretPosition = 0
        self._selections = []
        self._selectStartColumn = None
        self._selectStartIndex = None
        self._scrollTimer = None

        self._editMode = False
        self._activeEditWidget = None

        self.setFont(DefaultFont)
        self._dx = 0

        palette = QPalette(self.view.palette())
        palette.setColor(QPalette.Background, BackgroundColor)
        self.view.setPalette(palette)
        self.view.setAutoFillBackground(True)

        hex_column = HexColumnModel(self.editor, IntegerCodec(IntegerCodec.Format8Bit, False),
                                         IntegerFormatter(16, padding=2))
        address_bar = AddressColumnModel(hex_column)
        self.appendColumn(address_bar)
        self.appendColumn(hex_column)
        self.appendColumn(HexColumnModel(self.editor, IntegerCodec(IntegerCodec.Format8Bit, False),
                                         IntegerFormatter(16, padding=2)))
        # self.leadingColumn = hex_column

    @property
    def editor(self):
        return self._editor

    def setFont(self, new_font):
        QWidget.setFont(self, new_font)
        for column in self._columns:
            column.font = self.font()
        if self._activeEditWidget is not None:
            self._activeEditWidget.setFont(new_font)

    @property
    def leadingColumn(self):
        return self._leadingColumn

    @leadingColumn.setter
    def leadingColumn(self, new_column):
        if new_column is not self._leadingColumn:
            self._leadingColumn = new_column
            self.view.update()

    @property
    def caretPosition(self):
        return self._caretPosition

    @caretPosition.setter
    def caretPosition(self, new_pos):
        if self.caretPosition != new_pos:
            old_caret = self._caretPosition
            self._caretPosition = new_pos
            self.view.update()

    def caretIndex(self, column):
        return column.sourceModel.indexFromPosition(self.caretPosition) if column is not None else ModelIndex()

    def appendColumn(self, model):
        if model is not None:
            column = Column(model)
            column.font = self.font()

            column_dx = self._columns[-1].geometry.right() if self._columns else 0
            column.geometry = QRectF(column_dx, 0, 200, self.view.height())

            self._columns.append(column)

            column.updateRequested.connect(self._onColumnUpdateRequested)
            column.resizeRequested.connect(self._onColumnResizeRequested)

            if self._leadingColumn is None:
                self._leadingColumn = column
            else:
                column.scrollToFirstRow(self._leadingColumn.firstVisibleRow)

            self.view.update()

    def columnFromIndex(self, index):
        return first(cd for cd in self._columns if cd.sourceModel is index.model or cd.model is index.model)

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
        import time

        start = time.time()

        if self._editMode:
            self._updateActiveEditWidget()

        pd = self.PaintData()
        pd.painter = QPainter(self.view)
        pd.dirtyRect = event.rect()
        pd.dirtyRegion = event.region()

        for column in self._columns:
            self._paintColumn(pd, column)

        paint_time = time.time() - start
        # print('repainted in {0} s'.format(paint_time))

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

        painter.setPen(BorderColor)
        painter.drawLine(self._absoluteToWidget(QLineF(column.geometry.right(), 0, column.geometry.right(),
                                                       self.view.height())))

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
        if self._shouldShowVScroll:
            lc = self._leadingColumn
            max_value = max(lc.sourceModel.realRowCount() - 1, lc.firstVisibleRow)
            self.vScrollBar.setRangeLarge(0, max_value)
            self.vScrollBar.setPageStepLarge(lc.visibleRows)
            # self.vScrollBar.setSingleStepLarge(1)
            self.vScrollBar.setValueLarge(lc.firstVisibleRow)
        self.vScrollBar.setVisible(self._shouldShowVScroll)

        if self._shouldShowHScroll:
            self.hScrollBar.setRange(0, self._totalWidth - self.view.width())
            self.hScrollBar.setPageStep(self.view.width())
            self.hScrollBar.setSingleStep(10)
            self.hScrollBar.setValue(self._dx)
        self.hScrollBar.setVisible(self._shouldShowHScroll)

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

        dx = 0
        resized = False
        for column in self._columns:
            column.geometry.setLeft(dx)
            if column is column_to_resize:
                if column.geometry.width() != new_size.width():
                    column.geometry = QRectF(column.geometry.topLeft(), QSizeF(new_size.width(), column.geometry.height()))
                    resized = True
                else:
                    break
            dx += column.geometry.width()

        if resized:
            self.update()

    _nav_keys = (Qt.Key_Right, Qt.Key_Left, Qt.Key_Up, Qt.Key_Down, Qt.Key_Home, Qt.Key_End, Qt.Key_PageDown, Qt.Key_PageUp)

    def _keyPress(self, event):
        if event.key() in self._nav_keys:
            if self.leadingColumn is not None:
                caret_index = self.leadingColumn.sourceModel.indexFromPosition(self.caretPosition)
            else:
                caret_index = ModelIndex()

            new_caret_index = None
            data_model = self.leadingColumn.sourceModel

            if not event.modifiers() & Qt.ControlModifier and not event.modifiers() & Qt.AltModifier:
                if event.key() == Qt.Key_Right:
                    new_caret_index = caret_index.next
                elif event.key() == Qt.Key_Left:
                    new_caret_index = caret_index.previous
                elif event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
                    row_count = {
                        Qt.Key_Up: -1,
                        Qt.Key_Down: 1,
                        Qt.Key_PageUp: -(self.leadingColumn.fullVisibleRows - 1),
                        Qt.Key_PageDown: self.leadingColumn.fullVisibleRows - 1
                    }
                    new_row = caret_index.row + row_count[event.key()]
                    if new_row < 0:
                        new_row = 0
                    elif data_model.rowCount() >= 0 and new_row >= data_model.rowCount():
                        new_row = data_model.rowCount() - 1

                    while not new_caret_index and data_model.hasRow(new_row):
                        new_caret_index = data_model.index(new_row, caret_index.column)
                        if not new_caret_index:
                            new_caret_index = data_model.lastRowIndex(new_row)
                        new_row += 1
                elif event.key() == Qt.Key_Home:
                    new_caret_index = data_model.index(caret_index.row, 0)
                elif event.key() == Qt.Key_End:
                    new_caret_index = data_model.lastRowIndex(caret_index.row)
            elif event.modifiers() & Qt.ControlModifier:
                if event.key() == Qt.Key_Home:
                    new_caret_index = data_model.index(0, 0)
                elif event.key() == Qt.Key_End:
                    new_caret_index = data_model.lastRealIndex

            if not new_caret_index:
                return

            # make new caret position full-visible (even if caret is not moved)
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

            if (event.modifiers() & Qt.ShiftModifier and caret_index and not caret_index.virtual
                            and not new_caret_index.virtual):
                if not self._selectStartIndex:
                    self._selectStartIndex = caret_index
                    self._selectStartColumn = self.leadingColumn
                sel = self.selectionBetweenIndexes(new_caret_index, self._selectStartIndex)
                self._selections = [sel]
            else:
                self._selectStartIndex = None
                self._selectStartColumn = None

            self.update()

        elif event.key() == Qt.Key_Tab:
            self.loopLeadingColumn()
        elif event.key() == Qt.Key_Backtab:
            self.loopLeadingColumn(reverse=True)
        elif event.key() == Qt.Key_F2:
            if not self._editMode:
                self.startEditMode()

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
                self.leadingColumn = self._columns[column_index]

    def _mousePress(self, event):
        if event.button() == Qt.LeftButton:
            if self._activeEditWidget:
                self.endEditMode(False)

            mouse_pos = self._widgetToAbsolute(event.posF())
            column = self.columnFromPoint(mouse_pos)
            if column is not None:
                if column is not self.leadingColumn:
                    self.leadingColumn = column

                pos = self._absoluteToColumn(column, mouse_pos)
                activated_index = column.model.toSourceIndex(column.indexFromPoint(pos))
                if activated_index:
                    self.caretPosition = activated_index.data(ColumnModel.EditorPositionRole)

                    if not activated_index.virtual:
                        self._selectStartIndex = activated_index
                        self._selectStartColumn = column

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
                    selections = [self.selectionBetweenIndexes(self._selectStartIndex, hover_index)]
                    if selections != self._selections:
                        self._selections = selections
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

    _eventHandlers = {
        QEvent.Paint: _paint,
        QEvent.Wheel: _wheel,
        QEvent.Resize: _resize,
        QEvent.KeyPress: _keyPress,
        QEvent.MouseButtonPress: _mousePress,
        QEvent.MouseButtonRelease: _mouseRelease,
        QEvent.MouseMove: _mouseMove
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

    @property
    def editMode(self):
        return self._editMode

    class EditWidgetOptions(object):
        def __init__(self):
            self.font = None

    def startEditMode(self):
        if not self._editMode:
            caret_index = self._leadingColumn.sourceModel.indexFromPosition(self._caretPosition)
            # check if current index is editable
            if caret_index and caret_index.flags & ColumnModel.FlagEditable:
                # prepare data for edit widget: initialize options object
                widget_options = self.EditWidgetOptions()
                widget_options.font = self.font()

                # try to create edit widget
                edit_widget = self._leadingColumn.createEditWidget(self, caret_index, widget_options)
                if edit_widget is None or not isinstance(edit_widget, QWidget):
                    return
                self._activeEditWidget = edit_widget
                self._editMode = True

                self._updateActiveEditWidget()

                edit_widget.commitRequested.connect(self._onEditWidgetCommitRequested)
                edit_widget.rejectRequested.connect(self._onEditWidgetRejectRequested)
                edit_widget.nextRequested.connect(self._onEditWidgetNextRequested)

                self.view.setFocusProxy(edit_widget)
                self.view.setFocus()
                edit_widget.show()

    def endEditMode(self, commit_changes=False):
        if self._editMode:
            if commit_changes:
                self._activeEditWidget.commit()

            was_focus = self.view.hasFocus()
            self.view.setFocusProxy(None)
            self._activeEditWidget.deleteLater()
            self._activeEditWidget = None
            if was_focus:
                self.view.setFocus()

            self._editMode = False

    def _updateActiveEditWidget(self):
        if self._editMode:
            caret_index = self.caretIndex(self._leadingColumn)
            index_rect = self._columnToAbsolute(self._leadingColumn, self._leadingColumn.getRectForIndex(caret_index))

            # expand index rectangle for 4 pixels
            index_rect.setTop(index_rect.top() - 4)
            index_rect.setLeft(index_rect.left() - 4)
            index_rect.setRight(index_rect.right() + 4)
            index_rect.setBottom(index_rect.bottom() + 4)
            self._activeEditWidget.resize(index_rect.size().toSize())
            self._activeEditWidget.move(index_rect.topLeft().toPoint())

    def _onEditWidgetCommitRequested(self):
        self.endEditMode(True)

    def _onEditWidgetRejectRequested(self):
        self.endEditMode(False)

    def _onEditWidgetNextRequested(self, next_index, commit):
        if self._activeEditWidget is not None and next_index:
            reason = AbstractEditWidget.MoveReason
            if next_index == self.caretIndex(self._leadingColumn).next:
                reason = AbstractEditWidget.MoveNextReason
            elif next_index.next == self.caretIndex(self._leadingColumn):
                reason = AbstractEditWidget.MovePreviousReason

            self.caretPosition = next_index.data(ColumnModel.EditorPositionRole)
            self._activeEditWidget.setIndex(next_index, reason)


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


class AbstractEditWidget(object):
    UnknownReason, InitReason, MoveReason, MoveNextReason, MovePreviousReason = range(5)


class StandardTextEditWidget(QLineEdit, AbstractEditWidget):
    commitRequested = pyqtSignal()
    rejectRequested = pyqtSignal()
    nextRequested = pyqtSignal(ModelIndex, bool)

    def __init__(self, parent, index, style_options):
        QLineEdit.__init__(self, parent)

        palette = self.palette()
        palette.setColor(QPalette.Base, BackgroundColor)
        palette.setColor(QPalette.WindowText, TextColor)
        palette.setColor(QPalette.Highlight, SelectionBackgroundColor)
        palette.setColor(QPalette.HighlightedText, TextColor)
        self.setPalette(palette)

        self.setStyle(StandardTextEditWidgetProxyStyle(self.style()))
        self._updateCursorWidth()

        self.returnPressed.connect(self.commitRequested)
        self.cursorPositionChanged.connect(self._onCursorPositionChanged)
        self.textChanged.connect(self._updateCursorWidth)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left and self.cursorPosition() == 0:
            self.nextRequested.emit(self._index.previous, True)
        elif event.key() == Qt.Key_Right and self.cursorPosition() + 1 == len(self.text()):
            self.nextRequested.emit(self._index.next, True)
        elif event.key() == Qt.Key_Escape:
            self.rejectRequested.emit()
        else:
            QLineEdit.keyPressEvent(self, event)

    def _updateCursorWidth(self):
        fm = QFontMetricsF(self.font())
        cursor_pos = self.cursorPosition()
        if cursor_pos < len(self.text()):
            cursor_width = fm.width(self.text()[cursor_pos])
        else:
            cursor_width = -1
        self.style().cursorWidth = round(cursor_width)

    def _onCursorPositionChanged(self, old, new):
        if new >= len(self.text()) and self.text():
            self.setCursorPosition(len(self.text()) - 1)
        self._updateCursorWidth()


class HexColumnEditWidget(StandardTextEditWidget):
    def __init__(self, parent, index, style_options):
        StandardTextEditWidget.__init__(self, parent, index, style_options)
        self.formatter = index.model.formatter
        self.codec = index.model.valuecodec
        self.setValidator(FormatterValidator(self.formatter, self.codec))

        self.setIndex(index, self.InitReason)

    def setIndex(self, new_index, change_reason=AbstractEditWidget.UnknownReason):
        self.setText(new_index.data() if new_index else '')
        if change_reason in (self.MoveNextReason, self.UnknownReason, self.InitReason):
            self.setCursorPosition(0)
        elif change_reason == self.MovePreviousReason:
            self.setCursorPosition(len(self.text()) - 1)
        self._index = new_index

    def commit(self):
        if self._index:
            num = self.formatter.parse(self.text())
            self._index.model.setIndexData(self._index, self.codec.encode(num), ColumnModel.EditorDataRole)
        else:
            raise ValueError('invalid index')


class FormatterValidator(QValidator):
    def __init__(self, formatter, codec):
        QValidator.__init__(self)
        self.formatter = formatter
        self.codec = codec

    def validate(self, text, pos):
        import struct

        r1 = self.formatter.validate(text)
        if r1 == QValidator.Acceptable:
            try:
                self.codec.encode(self.formatter.parse(text))
                return r1, text, pos
            except struct.error:
                return QValidator.Invalid, text, pos
        return r1, text, pos


class StandardTextEditWidgetProxyStyle(ProxyStyle):
    def __init__(self, original_style):
        ProxyStyle.__init__(self, original_style)
        self.cursorWidth = -1

    def pixelMetric(self, metric, option, widget):
        if metric == self.PM_TextCursorWidth and self.cursorWidth >= 0:
            return self.cursorWidth
        return ProxyStyle.pixelMetric(self, metric, option, widget)
