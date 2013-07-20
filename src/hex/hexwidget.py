from PyQt4.QtCore import pyqtSignal, QObject, Qt, QPointF, QRectF, QPoint, QSizeF, QEvent, QTimer, QLineF, QUrl, \
                        QEasingCurve, QSequentialAnimationGroup, pyqtProperty, QPropertyAnimation
from PyQt4.QtGui import QColor, QFont, QFontMetricsF, QPolygonF, QWidget, QScrollBar, QVBoxLayout, QHBoxLayout, \
                        QPainter, QBrush, QPalette, QPen, QApplication, QRegion, QLineEdit, QValidator, \
                        QTextEdit, QTextOption, QSizePolicy, QStyle, QStyleOptionFrameV2, QTextCursor, QTextDocument, \
                        QTextBlockFormat, QPlainTextDocumentLayout, QAbstractTextDocumentLayout, QTextCharFormat, \
                        QTextTableFormat, QRawFont, QKeyEvent, QFontDatabase, QMenu, QToolTip, QPixmap, QIcon
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
import hex.resources.qrc_main
import hex.formatters as formatters


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

    def __add__(self, value):
        if not isinstance(value, int):
            return NotImplemented
        elif not self.valid:
            return ModelIndex()
        elif value == 0:
            return self
        else:
            return self.model.incrementedIndex(self, value)

    def __sub__(self, value):
        if isinstance(value, int):
            return self.__add__(-value)
        elif isinstance(value, ModelIndex):
            if not (self.valid and value.valid and value.model is self.model):
                raise ValueError()
            return self.model.subtractIndexes(self, value)
        else:
            return NotImplemented

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

    @property
    def offset(self):
        return self.model.indexOffset(self) if self else -1


class AbstractModel(QObject):
    def __init__(self):
        QObject.__init__(self)

    def rowCount(self):
        """Should return -1 if model has infinite number of rows."""
        raise NotImplementedError()

    def columnCount(self, row):
        """Should return -1 if no row exists"""
        raise NotImplementedError()

    def index(self, row, column):
        """Create index for row and column."""
        return ModelIndex(row, column, self) if self.hasIndex(row, column) else ModelIndex()

    def lastRowIndex(self, row):
        """Return last index on given row."""
        return self.index(row, self.columnCount(row) - 1)

    def indexFlags(self, index):
        return 0

    def indexData(self, index, role=Qt.DisplayRole):
        return None

    def hasIndex(self, row, column):
        """Return True if there is index at row and column in this model"""
        if row >= 0 and (self.rowCount() < 0 or row < self.rowCount()):
            return 0 <= column < self.columnCount(row)
        return False

    def hasRow(self, row):
        return row >= 0 and (self.rowCount() < 0 or row < self.rowCount())

    @property
    def firstIndex(self):
        """Return first index in the model"""
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
            row -= 1
        return index

    def setIndexData(self, index, value, role=Qt.EditRole):
        return False

    def incrementedIndex(self, index, value):
        if index and index.model is self and index.offset >= 0:
            if value == 0:
                return index
            return self.indexFromOffset(index.offset + value)
        return ModelIndex()

    def subtractIndexes(self, left, right):
        if left and right and left.model is self and right.model is self and left.offset >= 0 and right.offset >= 0:
            left_offset = left.offset
            right_offset = right.offset
            return left_offset - right_offset
        return NotImplemented

    def indexOffset(self, index):
        raise NotImplementedError()

    def indexFromOffset(self, offset):
        raise NotImplementedError()


class ColumnModel(AbstractModel):
    dataChanged = pyqtSignal(ModelIndex, ModelIndex)  # first argument is first changed index, second is last one
    dataResized = pyqtSignal(ModelIndex)  # argument is new last real index
    indexesInserted = pyqtSignal(ModelIndex, int)  # first argument is first inserted index
    indexesRemoved = pyqtSignal(ModelIndex, int)  # first argument is index BEFORE which indexes was removed, or
                                                  # ModelIndex is indexes was removed from model beginning
    modelReset = pyqtSignal()  # emitted when model is totally resetted
    headerDataChanged = pyqtSignal()

    EditorDataRole = Qt.UserRole + 1
    EditorPositionRole = Qt.UserRole + 2
    DataSizeRole = Qt.UserRole + 3

    FlagVirtual = 1
    FlagEditable = 2
    FlagModified = 4

    def __init__(self, editor=None):
        AbstractModel.__init__(self)
        self.name = ''
        self._editor = None
        self._editingIndex = None
        self.editor = editor

    def reset(self):
        self.modelReset.emit()
        self.headerDataChanged.emit()

    @property
    def editor(self):
        return self._editor

    @editor.setter
    def editor(self, new_editor):
        if self._editor is not new_editor:
            if self._editor is not None:
                with self._editor.lock.read:
                    self._editor.dataChanged.disconnect(self._onEditorDataChanged)
                    self._editor.resized.disconnect(self._onEditorDataResized)
                    self._editor.bytesInserted.disconnect(self._onEditorBytesInserted)
                    self._editor.bytesRemoved.disconnect(self._onEditorBytesRemoved)
                self._editor = None

            self._editor = new_editor
            if new_editor is not None:
                with new_editor.lock.read:
                    conn_mode = Qt.DirectConnection if utils.testRun else Qt.QueuedConnection
                    new_editor.dataChanged.connect(self._onEditorDataChanged, conn_mode)
                    new_editor.resized.connect(self._onEditorDataResized, conn_mode)
                    new_editor.bytesInserted.connect(self._onEditorBytesInserted, conn_mode)
                    new_editor.bytesRemoved.connect(self._onEditorBytesRemoved, conn_mode)

    @property
    def isInfinite(self):
        return self.rowCount() < 0

    def realRowCount(self):
        """Should return positive integer, infinite number of real rows is not allowed"""
        return self.rowCount()

    def realColumnCount(self, row):
        return self.columnCount(row)

    def lastRealRowIndex(self, row):
        return self.index(row, self.realColumnCount(row) - 1)

    def hasRealIndex(self, row, column):
        return (0 <= row < self.realRowCount()) and (0 <= column < self.realColumnCount(row))

    def headerData(self, section, role=Qt.DisplayRole):
        return None

    @property
    def lastRealIndex(self):
        row = self.realRowCount() - 1
        index = ModelIndex()
        while not index and row >= 0:
            index = self.lastRealRowIndex(row)
            row -= 1
        return index

    def _onEditorDataChanged(self, start, length):
        pass

    def _onEditorDataResized(self, new_size):
        pass

    def _onEditorBytesInserted(self, position, length):
        if self.regular and hasattr(self, 'regularCellDataSize'):
            start_index = self.indexFromPosition(position)
            if start_index:
                self.indexesInserted.emit(start_index, length // self.regularCellDataSize)

    def _onEditorBytesRemoved(self, position, length):
        if self.regular and hasattr(self, 'regularCellDataSize'):
            if position == 0:
                start_index = ModelIndex()
            else:
                start_index = self.indexFromPosition(position - 1)
            self.indexesRemoved.emit(start_index, length // self.regularCellDataSize)

    @property
    def preferSpaced(self):
        """Whether view should display indexes with spaces between them by default"""
        return True

    def indexFromPosition(self, position):
        """Return index matching given editor position. Can return virtual index"""
        raise NotImplementedError()

    @property
    def regular(self):
        """Return True if this model is regular. Regular models have same number of columns on each row
        (except last one, if one does exist) and same data size for each cell. Text length for cells can differ."""
        return False

    def beginEditIndex(self, index):
        """Should return tuple (ok, insert_mode)"""
        self._editingIndex = index

    def beginEditNewIndex(self, input_text, before_index):
        """Should return tuple (inserted_index, cursor_offset, insert_mode)"""
        pass

    def endEditIndex(self, save):
        self._editingIndex = None

    @property
    def editingIndex(self):
        return self._editingIndex

    def removeIndex(self, index):
        pos = index.data(self.EditorPositionRole)
        size = index.data(self.DataSizeRole)
        if pos < 0 or size < 0:
            raise ValueError()
        self.editor.remove(pos, size)

    def createValidator(self):
        """Validator is used to check values entered by user while editing column data. If createValidator returns
        None, all values will be considered valid."""
        return None

    def indexOffset(self, index):
        if self.regular and hasattr(self, 'regularCellDataSize'):
            if index and index.model is self:
                return index.row * self.regularColumnCount + index.column
        return -1

    def indexFromOffset(self, offset):
        if self.regular:
            return self.indexFromPosition(self.regularCellDataSize * offset)
        return ModelIndex()

    def nextEditableIndex(self, from_index):
        index = from_index.next
        while index and not index.flags & self.FlagEditable:
            index = index.next
        return index

    def previousEditableIndex(self, from_index):
        if not from_index:
            index = self.lastRealIndex
        else:
            index = from_index.previous
        while index and not index.flags & self.FlagEditable:
            index = index.previous
        return index


class RegularColumnModel(ColumnModel):
    def __init__(self, editor):
        ColumnModel.__init__(self, editor)
        self._rowCount = 0
        self._editingIndexText = ''
        self._editingIndexModified = False
        self._editingIndexInserted = False
        self.reset()

    @property
    def regularCellDataSize(self):
        raise NotImplementedError()

    @property
    def regularCellTextLength(self):
        return -1

    @property
    def regularColumnCount(self):
        raise NotImplementedError()

    def virtualIndexData(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and self.regularCellTextLength > 0:
            if self.editingIndex == index:
                return self.virtualIndexData(index, Qt.EditRole)
            else:
                return '.' * self.regularCellTextLength
        elif role == self.EditorDataRole:
            return bytes()

    def textForEditorData(self, editor_data, index, role=Qt.DisplayRole):
        raise NotImplementedError()

    def reset(self):
        self._updateRowCount()
        ColumnModel.reset(self)

    def rowCount(self):
        return -1

    def columnCount(self, row):
        return self.regularColumnCount

    def realRowCount(self):
        return self._rowCount

    def realCountCount(self):
        return self._rowCount

    @property
    def bytesOnRow(self):
        return self.columnsOnRow * self.regularCellDataSize

    def realColumnCount(self, row):
        if row < 0:
            return -1
        elif row + 1 == self._rowCount:
            count = (len(self.editor) % self.bytesOnRow) // self.regularCellDataSize
            return count or self.columnsOnRow
        elif row >= self._rowCount:
            return 0
        return self.columnsOnRow

    def indexFromPosition(self, editor_position):
        return self.index(int(editor_position // self.bytesOnRow),
                          int(editor_position % self.bytesOnRow) // self.regularCellDataSize)

    def indexData(self, index, role=Qt.DisplayRole):
        if not index or self.editor is None:
            return None
        editor_position = self.bytesOnRow * index.row + self.regularCellDataSize * index.column

        if role == self.EditorPositionRole:
            return editor_position
        elif role == self.DataSizeRole:
            return self.regularCellDataSize

        if editor_position >= len(self.editor):
            return self.virtualIndexData(index, role)

        if role == Qt.DisplayRole or role == Qt.EditRole:
            if self.editingIndex and self.editingIndex == index:
                return self._editingIndexText
            else:
                editor_data = self.editor.read(editor_position, self.regularCellDataSize)
                return self.textForEditorData(editor_data, role, index)
        elif role == self.EditorDataRole:
            return self.editor.read(editor_position, self.regularCellDataSize)
        elif role == self.DataSizeRole:
            return self.regularCellDataSize

    def setIndexData(self, index, value, role=Qt.EditRole):
        if self.editingIndex is None or self.editingIndex != index or role != Qt.EditRole:
            raise RuntimeError()
        if self._editingIndexText != value:
            self._editingIndexText = value
            self._editingIndexModified = True
            self.dataChanged.emit(index, index)

    def indexFlags(self, index):
        flags = self.FlagEditable
        if index.row >= self._rowCount or (index.row + 1 == self._rowCount and index > self.lastRealIndex):
            flags |= self.FlagVirtual
        elif self.editor is not None and self.editor.isRangeModified(index.data(self.EditorPositionRole),
                                                                     self.regularCellDataSize):
            flags |= self.FlagModified
        elif self.editingIndex and self.editingIndex == index and self._editingIndexModified:
            flags |= self.FlagModified
        return flags

    def headerData(self, section, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and 0 <= section < self.columnsOnRow:
            return formatters.IntegerFormatter(base=16).format(section * self.regularCellDataSize)

    def _onEditorDataChanged(self, start, length):
        length = length if length >= 0 else len(self.editor) - start
        self.dataChanged.emit(self.indexFromPosition(start), self.indexFromPosition(start + length - 1))

    def _onEditorDataResized(self, new_size):
        self._updateRowCount()
        self.dataResized.emit(self.lastRealIndex)

    @property
    def regular(self):
        return True

    def _updateRowCount(self):
        self._rowCount = len(self.editor) // self.bytesOnRow + bool(len(self.editor) % self.bytesOnRow)

    def beginEditIndex(self, index):
        if not self.editor.readOnly:
            edit_data = index.data(Qt.EditRole)
            index_text = index.data()
            self._editingIndexText = edit_data
            self._editingIndexModified = False
            self._editingIndexInserted = False
            ColumnModel.beginEditIndex(self, index)
            if edit_data != index_text:
                self.dataChanged.emit(index, index)
            return True, self.defaultCellInsertMode
        return False, False

    @property
    def defaultCellInsertMode(self):
        raise NotImplementedError()

    def _dataForNewIndex(self, input_text, before_index):
        raise NotImplementedError()

    def beginEditNewIndex(self, input_text, before_index):
        if not self.editor.readOnly and not self.editor.fixedSize:
            data_to_insert, index_text, cursor_offset = self._dataForNewIndex(input_text, before_index)
            position = before_index.data(self.EditorPositionRole) if before_index else len(self.editor)
            if data_to_insert and position >= 0:
                self.editor.insertSpan(position, DataSpan(self.editor, data_to_insert))
                new_index = self.indexFromPosition(position)
                self._editingIndexText = index_text
                self._editingIndexInserted = True
                self._editingIndexModified = True
                ColumnModel.beginEditIndex(self, new_index)
                return self.indexFromPosition(position), cursor_offset, self.defaultCellInsertMode
        return ModelIndex(), -1, False


class RegularValueColumnModel(RegularColumnModel):
    def __init__(self, editor, valuecodec, formatter, columns_on_row=16):
        self.valuecodec = valuecodec
        self.formatter = formatter
        self.columnsOnRow = columns_on_row
        RegularColumnModel.__init__(self, editor)

    @property
    def regularCellDataSize(self):
        return self.valuecodec.dataSize

    @property
    def regularColumnCount(self):
        return self.columnsOnRow

    def textForEditorData(self, editor_data, index, role=Qt.DisplayRole):
        import struct

        try:
            decoded = self.valuecodec.decode(editor_data)
        except struct.error:
            return '!' * self.regularCellTextLength if self.regularCellTextLength > 0 else '!'
        return self.formatter.format(decoded)

    def endEditIndex(self, save):
        if self.editingIndex:
            edited_index = self.editingIndex
            should_emit = True
            if save:
                position = self.indexData(self.editingIndex, self.EditorPositionRole)
                if position is None or position < 0:
                    raise ValueError('invalid position for index resolved')

                raw_data = self.valuecodec.encode(self.formatter.parse(self._editingIndexText))
                current_data = self.indexData(self.editingIndex, self.EditorDataRole)

                if raw_data != current_data:
                    self.editor.writeSpan(position, DataSpan(self.editor, raw_data))
            elif self._editingIndexInserted:
                self.removeIndex(self._editingIndex)
                should_emit = False
            else:
                self._editingIndexModified = False
                self._editingIndexInserted = False
                self._editingIndexText = ''

            RegularColumnModel.endEditIndex(self, save)
            if should_emit:
                self.dataChanged.emit(edited_index, edited_index)


def index_range(start_index, end_index, include_last=False):
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


class FrameModel(AbstractModel):
    """This model filters source ColumnModel to display only specified number of rows starting from given first row.
    FrameModel does not check if there are real source model rows corresponding to frame rows. Number of rows
    in this model always equal to frame size, even if source model has no enough rows to fill the frame.
    Frame can be scrolled and resized.
    """

    frameScrolled = pyqtSignal(int, int)  # first argument is new first frame row, second one is old first frame row
    frameResized = pyqtSignal(int, int)  # first argument is new frame size, second one is old frame size
    rowsUpdated = pyqtSignal(int, int)  # first argument is first modified frame row, second one is number of modified rows
                                # signal is emitted for rows that has been modified (and not emitted when frame scrolled)

    def __init__(self, source_model):
        AbstractModel.__init__(self)
        self._firstRow = 0
        self._rowCount = 0
        self._lastSourceIndex = source_model.lastRealIndex
        self.sourceModel = source_model
        self.sourceModel.dataChanged.connect(self._onDataChanged)
        self.sourceModel.dataResized.connect(self._onDataResized)
        self.sourceModel.modelReset.connect(self._onModelResetted)

    def scrollFrame(self, new_first_row):
        if self._firstRow != new_first_row:
            old_first_row = self._firstRow
            self._firstRow = new_first_row
            self.frameScrolled.emit(new_first_row, old_first_row)

    def resizeFrame(self, new_frame_size):
        if self._rowCount != new_frame_size:
            old_size = self._rowCount
            self._rowCount = new_frame_size
            self.frameResized.emit(new_frame_size, old_size)

    def rowCount(self):
        """Row count is always equal to frame size, even if source model has no enough rows to fill the frame"""
        return self._rowCount

    def columnCount(self, row):
        return max(self.sourceModel.columnCount(row + self._firstRow), 0)

    def index(self, row, column=0):
        return self.toFrameIndex(self.sourceModel.index(row + self._firstRow, column))

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
            return self.sourceModel.index(index.row + self._firstRow, index.column)
        else:
            return ModelIndex()

    def toFrameIndex(self, index):
        if not index or index.model is self:
            return index
        return AbstractModel.index(self, index.row - self._firstRow, index.column)

    def _onDataChanged(self, first_index, last_index):
        # check if update area lays inside frame
        if last_index.row < self._firstRow or first_index.row >= self._firstRow + self._rowCount:
            return
        first_row = first_index.row - self._firstRow
        self.rowsUpdated.emit(first_row, min(last_index.row - first_index.row + 1, self._rowCount - first_row))

    def _onDataResized(self, new_last_index):
        # as number of rows will not be affected, the only thing this can cause is updating some indexes.
        if not new_last_index:
            # boundary case: model has data and was cleared
            first_model_row = 0
            last_model_row = self._lastSourceIndex.row
        elif not self._lastSourceIndex:
            # boundary case: model was empty and was expanded
            first_model_row = 0
            last_model_row = new_last_index.row
        else:
            first_model_row = min(self._lastSourceIndex.row, new_last_index.row)
            last_model_row = max(self._lastSourceIndex.row, new_last_index.row)

        self._lastSourceIndex = new_last_index

        # now check if changes affect frame
        if not (last_model_row < self._firstRow or first_model_row >= self._firstRow + self._rowCount):
            self.rowsUpdated.emit(first_model_row - self._firstRow, last_model_row - first_model_row + 1)

    def _onModelResetted(self):
        self.rowsUpdated.emit(0, self._rowCount)


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
    """Document backend controls generation of QTextDocument html structure and interacts with underlying QTextDocument."""

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
        self._theme = DefaultTheme

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
    def editor(self):
        return self.dataModel.editor

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

    def paint(self, paint_data, is_leading):
        painter = paint_data.painter
        painter.save()

        painter.setPen(self._theme.textColor if is_leading else self._theme.inactiveTextColor)

        if settings.globalSettings()[appsettings.HexWidget_AlternatingRows]:
            for row_index in range(self._visibleRows):
                if (row_index + self._firstVisibleRow) % 2:
                    rect = self.rectForRow(row_index)
                    rect = QRectF(QPointF(0, rect.y()), QSizeF(self.geometry.width(), rect.height()))
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

    def paintCaret(self, paint_data, is_leading, caret_position, edit_mode):
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

    def paintSelection(self, paint_data, is_leading, selection):
        if selection:
            painter = paint_data.painter
            painter.setBrush(self._theme.selectionBackgroundColor)
            painter.setPen(QPen(QBrush(self._theme.selectionBorderColor), 2.0))
            for sel_polygon in self.polygonsForRange(self.dataModel.indexFromPosition(selection.startPosition),
                                        self.dataModel.indexFromPosition(selection.startPosition + selection.size - 1),
                                        join_lines=True):
                painter.drawPolygon(sel_polygon)

    def paintHighlight(self, paint_data, is_leading, hl_range, ignore_alpha):
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

    def paintHeader(self, paint_data, is_leading):
        # header can be painted only for regular columns
        if not self.showHeader:
            return

        painter = paint_data.painter
        painter.setPen(self._theme.headerTextColor if is_leading else self._theme.headerInactiveTextColor)

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
        """.format(mod_color=self._theme.modifiedTextColor.name()))

        return document

    @property
    def validator(self):
        return self.dataModel.createValidator()

    def rectForRow(self, row_index):
        return self._documentBackend.rectForRow(row_index).translated(self.documentOrigin)

    def translateIndex(self, index):
        return self.dataModel.indexFromPosition(index.data(ColumnModel.EditorPositionRole))


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
    insertModeChanged = pyqtSignal(bool)
    canUndoChanged = pyqtSignal(bool)
    canRedoChanged = pyqtSignal(bool)
    isModifiedChanged = pyqtSignal(bool)
    hasSelectionChanged = pyqtSignal(bool)
    leadingColumnChanged = pyqtSignal(object)
    showHeaderChanged = pyqtSignal(bool)
    urlChanged = pyqtSignal(object)

    MethodShowBottom, MethodShowTop, MethodShowCenter = range(3)

    def __init__(self, parent, editor):
        from hex.floatscrollbar import LargeScrollBar

        QWidget.__init__(self, parent)

        globalSettings = settings.globalSettings()

        global DefaultTheme
        if DefaultTheme is None:
            DefaultTheme = Theme()
            DefaultTheme.load(globalSettings, appsettings.HexWidget_DefaultTheme)

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

        self._editingIndex = None
        self._cursorVisible = False
        self._cursorOffset = 0
        self._cursorTimer = None
        self._blockCursor = globalSettings[appsettings.HexWidget_BlockCursor]
        self._insertMode = False
        self._cursorInsertMode = False

        self._showHeader = globalSettings[appsettings.HexWidget_ShowHeader]
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

        self.setFont(appsettings.getFontFromSetting(globalSettings[appsettings.HexWidget_Font]))

        from hex.hexcolumn import HexColumnModel
        from hex.charcolumn import CharColumnModel
        from hex.addresscolumn import AddressColumnModel
        from hex.floatcolumn import FloatColumnModel

        hex_column = HexColumnModel(self.editor, IntegerCodec(IntegerCodec.Format8Bit, False),
                                         IntegerFormatter(16, padding=2))
        address_bar = AddressColumnModel(hex_column)
        self.appendColumn(hex_column)
        self.insertColumn(address_bar, 0)

        self.appendColumn(CharColumnModel(self.editor, encodings.getCodec('ISO 8859-1'), self.font()))
        self.appendColumn(CharColumnModel(self.editor, encodings.getCodec('UTF-16le'), self.font()))
        self.leadingColumn = self._columns[1]

        conn_mode = Qt.DirectConnection if utils.testRun else Qt.QueuedConnection
        self.editor.canUndoChanged.connect(self.canUndoChanged, conn_mode)
        self.editor.canRedoChanged.connect(self.canRedoChanged, conn_mode)
        self.editor.isModifiedChanged.connect(self.isModifiedChanged, conn_mode)
        self.editor.urlChanged.connect(self.urlChanged, conn_mode)

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
            if self.editMode:
                old_caret_index = self.caretIndex(self._leadingColumn)
            self._caretPosition = new_pos
            if self.editMode:
                new_caret_index = self.caretIndex(self._leadingColumn)
                if new_caret_index != old_caret_index:
                    self.endEditIndex(save=True)
                    self.beginEditIndex(new_caret_index)
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
        return column.dataModel.indexFromPosition(self.caretPosition) if column is not None else ModelIndex()

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
            column.paintHighlight(pd, self._leadingColumn is column, bookmark, True)

        if self._leadingColumn is not None and self._emphasizeRange is not None:
            column.paintHighlight(pd, self._leadingColumn is column, self._emphasizeRange, False)

        column.paint(pd, self._leadingColumn is column)

        column.paintCaret(pd, self._leadingColumn is column, self._caretPosition,
                          (self.editMode and self._leadingColumn is column))

        # paint selections
        if not self.editMode or self._leadingColumn is not column:
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
        Scrolls by as much rows as possible."""
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
        for column in self._columns:
            self.syncColumnFrame(column, sync_row)

    def syncColumnFrame(self, column, sync_row=0):
        if self.leadingColumn is not None and column is not None and column is not self.leadingColumn:
            editor_position = self.leadingColumn.frameModel.index(sync_row, 0).data(ColumnModel.EditorPositionRole)
            if editor_position is not None:
                # position frame of non-leading column so same data will be on same row
                sync_index = column.dataModel.indexFromPosition(editor_position)
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
            if int(value) != self._leadingColumn.firstVisibleRow:
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

        self.view.update()

    _edit_keys = (Qt.Key_Backspace, Qt.Key_Delete)

    def _keyPress(self, event):
        method = None
        if event.key() == Qt.Key_Right:
            method = self.NavMethod_NextCell if not self.editMode else self.NavMethod_NextCharacter
        elif event.key() == Qt.Key_Left:
            method = self.NavMethod_PrevCell if not self.editMode else self.NavMethod_PrevCharacter
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
                method = self.NavMethod_RowStart if not self.editMode else self.NavMethod_CellStart
        elif event.key() == Qt.Key_End:
            if event.modifiers() & Qt.ControlModifier:
                method = self.NavMethod_EditorEnd
            else:
                method = self.NavMethod_RowEnd if not self.editMode else self.NavMethod_CellEnd

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
        # input text into active cell
        index = self.caretIndex(self._leadingColumn)
        cursor_offset = self._cursorOffset
        if index:
            original_index_text = index.data(Qt.EditRole)
            index_text = None
            nav_method = None

            if event.key() == Qt.Key_Backspace:
                if cursor_offset == 0:
                    # this behavious can be unexpected sometimes...
                    # index_to_remove = index.previous
                    # if index_to_remove and not index_to_remove.virtual:
                    #     self._leadingColumn.dataModel.removeIndex(index_to_remove)
                    #     self._navigate(self.NavMethod_PrevCell)
                    #     self._cursorOffset = 0
                    #     return
                    pass
                elif self._cursorInsertMode:
                    index_text = original_index_text[:cursor_offset-1] + original_index_text[cursor_offset:]
                    nav_method = self.NavMethod_PrevCharacter
            elif event.key() == Qt.Key_Delete:
                if self._cursorInsertMode and cursor_offset < len(original_index_text):
                    index_text = original_index_text[:cursor_offset] + original_index_text[cursor_offset+1:]
            elif event.text():
                if cursor_offset == 0 and self._insertMode and not self._cursorInsertMode:
                    # when in insert mode, pressing character key when cursor is at beginning of cell inserts new cell
                    self._leadingColumn.dataModel.endEditIndex(False)
                    inserted_index, cursor_offset, insert_mode = self._leadingColumn.dataModel.beginEditNewIndex(
                                                                                                    event.text(), index)
                    if inserted_index:
                        self._editingIndex = inserted_index
                        self._cursorInsertMode = insert_mode

                        max_cursor_offset = len(inserted_index.data()) if insert_mode else len(inserted_index.data()) - 1
                        if cursor_offset > max_cursor_offset:
                            self._goCaretIndex(self.findNextEditableIndex(index))
                            self._cursorOffset = 0
                        else:
                            self._cursorOffset = cursor_offset
                        return
                elif self._cursorInsertMode:
                    # otherwise, insert character at cursor offset
                    index_text = original_index_text[:cursor_offset] + event.text() + original_index_text[cursor_offset:]
                    nav_method = self.NavMethod_NextCharacter
                else:
                    # if text overwrite mode is enabled, replace character at cursor offset
                    index_text = original_index_text[:cursor_offset] + event.text() + original_index_text[cursor_offset+1:]
                    nav_method = self.NavMethod_NextCharacter

            if index_text is not None:
                validator = self._leadingColumn.validator
                new_cursor_offset = None
                if validator is not None:
                    status, text, new_cursor_offset = validator.validate(index_text, cursor_offset, original_index_text)
                    if status == QValidator.Invalid:
                        return
                    if text is not None:
                        index_text = text
                    if new_cursor_offset is not None:
                        if new_cursor_offset > self._editingCellMaximalCursorOffset:
                            nav_method = self.NavMethod_NextCell
                            new_cursor_offset = 0

                index.setData(index_text, Qt.EditRole)

                if new_cursor_offset is not None:
                    self._cursorOffset = new_cursor_offset
                elif nav_method is not None:
                    self._navigate(nav_method)

    (NavMethod_NextCell, NavMethod_PrevCell, NavMethod_RowStart, NavMethod_RowEnd, NavMethod_ScreenUp,
        NavMethod_ScreenDown, NavMethod_RowUp, NavMethod_RowDown, NavMethod_EditorStart, NavMethod_EditorEnd,
        NavMethod_NextCharacter, NavMethod_PrevCharacter, NavMethod_CellEnd, NavMethod_CellStart) = range(14)

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

    def _goEditorStart(self):
        self._goCaretIndex(self._leadingColumn.dataModel.index(0, 0))

    def _goEditorEnd(self):
        self._goCaretIndex(self._leadingColumn.dataModel.lastRealIndex)

    @property
    def _editingCellMaximalCursorOffset(self):
        if self._editingIndex:
            return len(self._editingIndex.data()) if self._cursorInsertMode else len(self._editingIndex.data()) - 1

    def _goNextCharacter(self):
        caret_index = self.caretIndex(self._leadingColumn)

        new_caret_index = caret_index
        new_cursor_offset = self._cursorOffset + 1

        if new_cursor_offset > self._editingCellMaximalCursorOffset:
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
        if caret_index.row < new_caret_index.row:
            method = self.MethodShowBottom
        elif caret_index.row > new_caret_index.row:
            method = self.MethodShowTop
        else:
            method = self.MethodShowCenter

        self.makeIndexVisible(new_caret_index, method)

        if new_caret_index != caret_index:
            self.caretPosition = new_caret_index.data(ColumnModel.EditorPositionRole)

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
                        if cursor_offset < self._editingCellMaximalCursorOffset:
                            self.cursorOffset = cursor_offset
                    else:
                        self.endEditIndex(True)
                        self.caretPosition = activated_index.data(ColumnModel.EditorPositionRole)

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
                            sel = self.selectionBetweenIndexes(proxy.dataModel.indexFromPosition(sel.startPosition),
                                                               proxy.dataModel.indexFromPosition(sel.startPosition + sel.size - 1))
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
                    offset = column.cursorPositionFromPoint(self._absoluteToColumn(column, mouse_pos))
                    self.cursorOffset = min(self._editingCellMaximalCursorOffset, max(offset, 0))

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

    @property
    def editMode(self):
        return bool(self._editingIndex)

    @property
    def editingIndex(self):
        return self._editingIndex

    def beginEditIndex(self, index=None):
        if index is None:
            index = self.caretIndex(self._leadingColumn)

        if index and index.flags & ColumnModel.FlagEditable:
            if self.editMode:
                if self.editingIndex == index:
                    return
                else:
                    self.endEditIndex(save=True)

            ok, text_insert_mode = index.model.beginEditIndex(index)
            if ok:
                self._editingIndex = index
                self._cursorInsertMode = text_insert_mode
                self._cursorOffset = 0
                self._cursorVisible = True

                self._cursorTimer = QTimer()
                self._cursorTimer.timeout.connect(self._toggleCursor)
                self._cursorTimer.start(QApplication.cursorFlashTime())

                self.view.update()

    def endEditIndex(self, save):
        if self._editingIndex:
            self._editingIndex.model.endEditIndex(save)

            self._editingIndex = None
            self._cursorInsertMode = False
            self._cursorOffset = 0
            self._cursorVisible = False

            self._cursorTimer.stop()
            self._cursorTimer = None
            self.view.update()

    def selectAll(self):
        if self.editor is not None and self._leadingColumn is not None:
            first_index = self._leadingColumn.dataModel.firstIndex
            last_index = self._leadingColumn.dataModel.lastRealIndex
            if first_index and last_index:
                sel_range = SelectionRange(self, first_index, last_index - first_index + 1,
                                           SelectionRange.UnitCells, SelectionRange.BoundToData)
                self.selectionRanges = [sel_range]

    def copy(self):
        if len(self._selections) == 1:
            from hex.clipboard import Clipboard

            clb = Clipboard()
            clb.copy(self.editor, self._selections[0].startPosition, self._selections[0].size)

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
                    self._editor.remove(selection.startPosition, selection.size)
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
        if self.editMode and self._cursorVisible and self.isIndexVisible(self.caretIndex(self._leadingColumn)):
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
        if self.editMode and self._cursorVisible and self.isIndexVisible(caret_index):
            return self._columnToAbsolute(self._leadingColumn,
                                          self._leadingColumn.cursorPositionInIndex(caret_index, self._cursorOffset))
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
        return from_index.model.nextEditableIndex(from_index)

    def findPreviousEditableIndex(self, from_index):
        return from_index.model.previousEditableIndex(from_index)

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
            self.editor.remove(selection.startPosition, selection.size)

    def fillSelected(self, pattern):
        for selection in self._selections:
            self.editor.writeSpan(selection.startPosition, FillSpan(self.editor, pattern, selection.size))
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
            column.dataModel.reset()

    @property
    def url(self):
        return self.editor.url if self.editor is not None else QUrl()

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
    despite editor data modifications. When bound to data, inserting or removing data before range start shifts range
    start position; removing data inside range leads to collapsing range size.
    """

    UnitBytes, UnitCells = range(2)
    BoundToData, BoundToPosition = range(2)

    moved = pyqtSignal(object, object)
    resized = pyqtSignal(int, int)
    updated = pyqtSignal()

    def __init__(self, hexwidget, start=-1, length=0, unit=UnitBytes, bound_to=BoundToData):
        """When unit == UnitBytes, start should be editor position (int), if unit == UnitCells, start should be ModelIndex
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
                self._hexWidget.editor.bytesInserted.connect(self._onInserted)
                self._hexWidget.editor.bytesRemoved.connect(self._onRemoved)
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
            pos = self.start.data(ColumnModel.EditorPositionRole)
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
                last_pos = last_index.data(ColumnModel.EditorPositionRole) + last_index.data(ColumnModel.DataSizeRole)
                return last_pos - first_index.data(ColumnModel.EditorPositionRole)
            elif first_index:
                return len(self._model.editor) - first_index.data(ColumnModel.EditorPositionRole)
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

    def __ne__(self, other):
        if not isinstance(other, DataRange):
            return NotImplemented
        return not self.__eq__(self, other)

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
        self._backgroundColor = QColor(Qt.red)

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

    @property
    def backgroundColor(self):
        return self._backgroundColor
