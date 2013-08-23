import struct
import math
from PyQt4.QtCore import Qt, QObject, pyqtSignal, QEvent
from PyQt4.QtGui import QValidator
import hex.utils as utils
import hex.formatters as formatters
import hex.valuecodecs as valuecodecs
import hex.documents as documents

# Why we need to make different model classes? Why not to use existing ones?
# These classes are specialized and optimized for our needs. Main cause is that custom model represents irregular
# array instead of tree-like structure Qt does. Another difference is that Qt classes will not work with very big
# amount of data on 32-bit machines where number of rows can exceed 32-bit integer limit.


class ModelIndex(object):
    def __init__(self, row=-1, column=-1, model=None, internal_data=None):
        self.__row = row
        self.__column = column
        self.__model = model
        self.__data = internal_data

    @property
    def row(self):
        """This value is always positive int or 0 for valid indexes, -1 for invalid ones"""
        return self.__row if self.valid else -1

    @property
    def column(self):
        """This value is always positive int or 0 for valid indexes, -1 for invalid ones"""
        return self.__column if self.valid else -1

    @property
    def model(self):
        """Returns model this index belongs to, None for invalid indexes"""
        return self.__model if self.valid else None

    @property
    def virtual(self):
        # virtual index does not represent real data, but used to represent empty cells in regular models.
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
        """Note that invalid index is always equal only to another invalid index, even if these indexes are
        logically belong to another model."""
        if not isinstance(other, ModelIndex):
            return NotImplemented

        if not self.valid:
            return not other.valid
        elif not other.valid:
            return not self.valid

        return self.row == other.row and self.column == other.column and self.model is other.model

    def __bool__(self):
        return self.valid

    def __lt__(self, other):
        """Invalid index is always smaller than any valid index, but not smaller than another invalid index
        """

        if not isinstance(other, ModelIndex):
            return NotImplemented

        if not self.valid:
            return other.valid
        elif not other.valid:
            return False

        return self.offset < other.offset

    def __le__(self, other):
        less = self.__lt__(other)
        equal = self.__eq__(other)
        if less == NotImplemented or equal == NotImplemented:
            return NotImplemented
        return less or equal

    def __add__(self, value):
        """You can add integer value to index to iterate over model indexes"""

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
            if not self.valid and not value.valid:
                return 0
            elif not self.valid or not value.valid:
                raise ValueError('__sub__ cannot process invalid and valid indexes together')
            else:
                return self.model.subtractIndexes(self, value)
        else:
            return NotImplemented

    @property
    def next(self):
        return self + 1

    @property
    def previous(self):
        return self - 1

    @property
    def offset(self):
        return self.model.indexOffset(self) if self.valid else -1

    @property
    def documentPosition(self):
        return self.data(ColumnModel.DocumentPositionRole)

    @property
    def documentData(self):
        return self.data(ColumnModel.DocumentDataRole)

    @property
    def dataSize(self):
        return self.data(ColumnModel.DataSizeRole)


class AbstractModel(QObject):
    def __init__(self):
        QObject.__init__(self)

    def rowCount(self) -> int:
        """Should return positive number of rows, including rows consisting of virtual indexes."""
        raise NotImplementedError()

    def realRowCount(self):
        """Should return number of real rows (row is real if has at least one real index)"""
        return self.rowCount()

    def columnCount(self, row) -> int:
        """Should return -1 if row index is invalid (< 0 or > rowCount())"""
        raise NotImplementedError()

    def realColumnCount(self, row):
        """Should return number of real indexes in row, starting from beginning. Row cannot have real indexes
        in middle or end of row, or real indexes separated by virtual ones.
        """
        return self.columnCount(row)

    def index(self, row, column):
        """Create index for row and column."""
        return ModelIndex(row, column, self) if self.hasIndex(row, column) else ModelIndex()

    def lastRowIndex(self, row):
        """Return last index on given row."""
        return self.index(row, self.columnCount(row) - 1)

    def lastRealRowIndex(self, row):
        return self.index(row, self.realColumnCount(row) - 1)

    def indexFlags(self, index):
        return 0

    def indexData(self, index, role=Qt.DisplayRole) -> object:
        raise NotImplementedError()

    def hasIndex(self, row, column):
        """Return True if there is index at row and column in this model"""
        if 0 <= row < self.rowCount():
            return 0 <= column < self.columnCount(row)
        return False

    def hasRow(self, row):
        return 0 <= row < self.rowCount()

    def hasRealIndex(self, row, column):
        return (0 <= row < self.realRowCount()) and (0 <= column < self.realColumnCount(row))

    def headerData(self, section, role=Qt.DisplayRole):
        return None

    @property
    def firstIndex(self):
        """Return first index in the model"""
        return self.index(0, 0)

    @property
    def firstRealIndex(self):
        index = self.index(0, 0)
        return index if not index.virtual else ModelIndex()

    @property
    def lastIndex(self):
        """Return last index in the model"""
        row = self.rowCount() - 1
        index = ModelIndex()
        while not index and row >= 0:
            index = self.lastRowIndex(row)
            row -= 1
        return index

    @property
    def lastRealIndex(self):
        row = self.realRowCount() - 1
        index = ModelIndex()
        while not index and row >= 0:
            index = self.lastRealRowIndex(row)
            row -= 1
        return index

    def incrementedIndex(self, index, value):
        if index and index.model is self and index.offset >= 0:
            if value == 0:
                return index
            return self.indexFromOffset(index.offset + value)
        return ModelIndex()

    def subtractIndexes(self, left, right):
        if left and right and left.model is self and right.model is self and left.offset >= 0 and right.offset >= 0:
            return left.offset - right.offset
        raise NotImplementedError()

    def indexOffset(self, index) -> int:
        raise NotImplementedError()

    def indexFromOffset(self, offset) -> int:
        raise NotImplementedError()


class StandardEditDelegate(QObject):
    """Delegate allows to edit indexes in model. Delegate can specify insert mode for index.
    Note that insert mode for editing index is not same as insert mode for HexWidget - first one
    defines if character from user input will overwrite existing ones or will be inserted, while insert mode
    for HexWidget determines whether new indexes will be inserted into model on certain events.
    Also, delegate can specify initial cursor offset for index.
    """

    dataChanged = pyqtSignal()
    finished = pyqtSignal(bool)
    cursorMoved = pyqtSignal(int)
    requestFinish = pyqtSignal(bool, int)   # (should_be_saved, next_index_to_edit)

    EditNextIndex, EditPreviousIndex, EditNone = range(3)

    def __init__(self, index, is_inserted, init_text=None, insert_mode=False, cursor_offset=0):
        QObject.__init__(self)
        self.index = index
        self.insertMode = insert_mode
        self._cursorOffset = 0
        self.modified = is_inserted or (init_text is not None and init_text != index.data(Qt.EditRole))
        self.isInserted = is_inserted
        self._text = init_text if init_text is not None else index.data(Qt.EditRole)

        if cursor_offset < self.minimalCursorOffset:
            self._cursorOffset = self.minimalCursorOffset
        elif cursor_offset > self.maximalCursorOffset:
            self._cursorOffset  = self.maximalCursorOffset
        else:
            self._cursorOffset = cursor_offset

        validator = self.createValidator()
        if validator is not None:
            status = validator.validate(self._text, cursor_offset)
            if status == QValidator.Invalid:
                raise ValueError()

    @property
    def cursorOffset(self):
        return self._cursorOffset

    @cursorOffset.setter
    def cursorOffset(self, new_offset):
        if self._cursorOffset != new_offset and self.minimalCursorOffset <= new_offset <= self.maximalCursorOffset:
            self._cursorOffset = new_offset
            self.cursorMoved.emit(new_offset)

    @property
    def maximalCursorOffset(self):
        return len(self._text) if self.insertMode else max(0, len(self._text) - 1)

    @property
    def minimalCursorOffset(self):
        return 0

    def end(self, save) -> None:
        """Called by HexWidget before it finishes editing of index. If :save: is False, delegate should
        correctly cancel all changes made to model. Default implementation removes index if it was inserted."""
        if save and (self.modified or self.index.virtual):
            self.index.model._saveData(self)
        elif self.isInserted:
            self.index.model.removeIndex(self.index)
        self.finished.emit(save)

    def data(self, role=Qt.EditRole) -> object:
        """Default implementation replaces index data for Qt.EditRole and Qt.DisplayRole with user-inputted text.
        """
        if role == Qt.DisplayRole or role == Qt.EditRole:
            return self._text
        else:
            return self.index.data(role)

    @property
    def flags(self) -> int:
        """Default implementation adds FlagModified is text was modified by user.
        """
        flags = self.index.flags
        flags &= ~ColumnModel.FlagBroken
        return ColumnModel.FlagModified | flags if self.modified else flags

    def _setData(self, value, new_cursor_pos=None):
        """Writes data for index. Does not write data to document. Returns True on success.
        """
        if value == self._text:
            return True

        validator = self.createValidator()
        if validator is None or validator.validate(value, self.cursorOffset):
            self._text = value
            self.modified = True
            self.dataChanged.emit()
            return True
        return False

    def insertText(self, text):
        if self._setData(self._text[:self._cursorOffset] + text + self._text[self._cursorOffset:]):
            self.moveCursorRight()
            return True
        return False

    def overwriteText(self, text):
        if self._setData(self._text[:self._cursorOffset] + text + self._text[self._cursorOffset+1:]):
            self.moveCursorRight()
            return True
        return False

    def backspaceChar(self):
        if self.cursorOffset <= self.minimalCursorOffset:
            return False
        new_text = self._text[:self.cursorOffset-1] + self._text[self.cursorOffset:]
        if self._setData(new_text):
            self.moveCursorLeft()
        return True

    def deleteChar(self):
        if self.cursorOffset >= self.maximalCursorOffset:
            return False
        new_text = self._text[:self._cursorOffset] + self._text[self._cursorOffset+1:]
        return self._setData(new_text)

    def createValidator(self):
        return self.index.model.createValidator() if self.index else None

    @property
    def hasNextEditIndex(self):
        """Can be called BEFORE delegate data is saved"""
        return bool(self.nextEditIndex)

    @property
    def nextEditIndex(self):
        """Looks for next index to edit after editing of current index was finished. By reimplementing this function
        you can implement editing in regular columns where change in one index data can cause changes in another
        indexes (for example, utf-8 character column). Default implementation return next index that has
        ColumnModel.FlagEditable set.
        """
        index = self.index.next
        while index and not index.flags & ColumnModel.FlagEditable:
            index = index.next
        return index

    @property
    def hasPreviousEditIndex(self):
        """Can be called BEFORE delegate data is saved."""
        return bool(self.previousEditIndex)

    @property
    def previousEditIndex(self):
        """Same as nextEditIndex, but searches backward.
        """
        index = self.index.previous
        while index and not index.flags & ColumnModel.FlagEditable:
            index = index.previous
        return index

    def handleEvent(self, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Right:
                self.moveCursorRight()
            elif event.key() == Qt.Key_Left:
                self.moveCursorLeft()
            elif event.key() == Qt.Key_Home:
                self.cursorOffset = self.minimalCursorOffset
            elif event.key() == Qt.Key_End:
                self.cursorOffset = self.maximalCursorOffset
            elif event.key() == Qt.Key_Delete:
                if self.insertMode:
                    return self.deleteChar()
            elif event.key() == Qt.Key_Backspace:
                if self.insertMode:
                    return self.backspaceChar()
            elif event.text():
                if self.insertMode:
                    self.insertText(event.text())
                else:
                    self.overwriteText(event.text())
                return True
        return False

    def moveCursorRight(self):
        new_offset = self.cursorOffset + 1
        if new_offset > self.maximalCursorOffset:
            self.requestFinish.emit(True, self.EditNextIndex)
        else:
            self.cursorOffset = new_offset

    def moveCursorLeft(self):
        new_offset = self.cursorOffset - 1
        if new_offset < self.minimalCursorOffset:
            self.requestFinish.emit(True, self.EditPreviousIndex)
        else:
            self.cursorOffset = new_offset


class ColumnModel(AbstractModel):
    dataChanged = pyqtSignal(ModelIndex, ModelIndex)  # first argument is first changed index, second is last one
    dataResized = pyqtSignal(ModelIndex)              # argument is new last real index
    indexesInserted = pyqtSignal(ModelIndex, object)     # first argument is first inserted index
    indexesRemoved = pyqtSignal(ModelIndex, object)      # first argument is index BEFORE which indexes was removed, or
                                                      # ModelIndex() if indexes was removed from model beginning
    modelReset = pyqtSignal()                         # emitted when model is resetted
    headerDataChanged = pyqtSignal()

    DocumentDataRole = Qt.UserRole + 1                # byte array of data represented by index
    DocumentPositionRole = Qt.UserRole + 2            # start of index data in document
    DataSizeRole = Qt.UserRole + 3                    # length of data represented by index

    FlagVirtual = 1
    FlagEditable = 2
    FlagModified = 4
    FlagBroken = 8                                    # indexes that represent logically invalid data should have
                                                      #  this flag

    def __init__(self, document=None):
        AbstractModel.__init__(self)
        self.name = ''
        self._document = None
        self.document = document

    def reset(self):
        """This function should be called after cardinal changes in column structure, for example,
        column settings changes.
        """
        self.modelReset.emit()
        self.headerDataChanged.emit()

    @property
    def document(self):
        return self._document

    @document.setter
    def document(self, new_document):
        if self._document is not new_document:
            if self._document is not None:
                with utils.readlock(self._document.lock):
                    self._document.dataChanged.disconnect(self._onDocumentDataChanged)
                    self._document.resized.disconnect(self._onDocumentDataResized)
                    self._document.bytesInserted.disconnect(self._onDocumentBytesInserted)
                    self._document.bytesRemoved.disconnect(self._onDocumentBytesRemoved)
                self._document = None

            self._document = new_document
            if new_document is not None:
                with utils.readlock(new_document.lock):
                    conn_mode = Qt.DirectConnection if utils.testRun else Qt.QueuedConnection
                    new_document.dataChanged.connect(self._onDocumentDataChanged, conn_mode)
                    new_document.resized.connect(self._onDocumentDataResized, conn_mode)
                    new_document.bytesInserted.connect(self._onDocumentBytesInserted, conn_mode)
                    new_document.bytesRemoved.connect(self._onDocumentBytesRemoved, conn_mode)

    def _onDocumentDataChanged(self, start, length):
        pass

    def _onDocumentDataResized(self, new_size):
        pass

    def _onDocumentBytesInserted(self, position, length):
        pass

    def _onDocumentBytesRemoved(self, position, length):
        pass

    @property
    def preferSpaced(self):
        """Whether view should display indexes with spaces between them by default"""
        return True

    def indexFromPosition(self, position) -> ModelIndex:
        """Return index matching given document position. Can return virtual index"""
        raise NotImplementedError()

    @property
    def regular(self):
        """Return True if this model is regular. Regular models have same number of columns on each row
        (except last one) and same data size for each cell. Text length for cells can differ."""
        return False

    def delegateForIndex(self, index) -> StandardEditDelegate:
        """Should return delegate to edit given index. If None is returned, HexWidget cancels editing.
        """
        raise NotImplementedError()

    def delegateForNewIndex(self, input_text, before_index) -> StandardEditDelegate:
        """Should return delegate to edit new index. After calling this function, new index should be already
        inserted into model.
        """
        raise NotImplementedError()

    def _saveData(self, delegate) -> bool:
        raise NotImplementedError()

    def removeIndex(self, index):
        pos = index.data(self.DocumentPositionRole)
        size = index.data(self.DataSizeRole)
        if pos < 0 or size < 0:
            raise ValueError()
        self.document.remove(pos, size)

    def createValidator(self):
        """Validator is used to check values entered by user while editing column data. If createValidator returns
        None, all values will be considered valid."""
        return None


class RegularColumnModel(ColumnModel):
    def __init__(self, document, delegate_type=StandardEditDelegate):
        ColumnModel.__init__(self, document)
        self._delegateType = delegate_type

    @property
    def regularDataSize(self) -> int:
        """Should return number of bytes represented by each index"""
        raise NotImplementedError()

    @property
    def regularTextLength(self) -> int:
        """Should return length of text that each index has. If text length can vary, should return -1"""
        return -1

    @property
    def regularColumnCount(self) -> int:
        """Return number of columns on each row. Note that number of columns on last row can differ from
        this value"""
        raise NotImplementedError()

    def virtualIndexData(self, index, role=Qt.DisplayRole):
        """Return data for virtual index. Default implementation handles DocumentDataRole."""
        if role == Qt.DisplayRole:
            return '.' * max(1, self.regularTextLength)
        elif role == self.DocumentDataRole:
            return bytes()

    def textForDocumentData(self, document_data, index, role=Qt.DisplayRole) -> object:
        """Reimplement this method instead of indexData to return data for given index. You do not need to
        process DocumentPositionRole, DocumentSizeRole, DocumentDateRole roles.
        """
        raise NotImplementedError()

    def reset(self):
        ColumnModel.reset(self)

    def rowCount(self):
        return utils.MaximalPosition // self.bytesOnRow + 1

    def columnCount(self, row):
        if row + 1 == self.rowCount():
            return math.ceil(((utils.MaximalPosition + 1) % self.bytesOnRow) / self.regularDataSize)
        return self.regularColumnCount if self.hasRow(row) else -1

    def realRowCount(self):
        document_length = self.document.length
        if document_length == 0:
            return 0
        return (document_length - 1) // self.bytesOnRow + 1

    @property
    def bytesOnRow(self):
        return self.regularColumnCount * self.regularDataSize

    def realColumnCount(self, row):
        if not self.hasRow(row):
            return -1
        elif row + 1 == self.realRowCount():
            # last row in model
            count = (self.document.length % self.bytesOnRow) // self.regularDataSize
            return count or self.regularColumnCount
        elif row >= self.realRowCount():
            return 0
        else:
            return self.regularColumnCount

    def indexFromPosition(self, document_position):
        return self.index(int(document_position // self.bytesOnRow),
                          int(document_position % self.bytesOnRow) // self.regularDataSize)

    def indexData(self, index, role=Qt.DisplayRole):
        """Note that even for regular columns length of data for DocumentDataRole can differ from regularDataSize
        value in case of virtual indexes. But DocumentDataSize is always equal to regularDataSize, even for virtual
        indexes.
        """

        if not index or self.document is None:
            return None
        document_position = self.bytesOnRow * index.row + self.regularDataSize * index.column

        if role == self.DocumentPositionRole:
            return document_position
        elif role == self.DataSizeRole:
            return self.regularDataSize

        if document_position >= self.document.length:
            return self.virtualIndexData(index, role)

        if role == Qt.DisplayRole or role == Qt.EditRole:
            document_data = self.document.read(document_position, self.regularDataSize)
            return self.textForDocumentData(document_data, index, role)
        elif role == self.DocumentDataRole:
            return self.document.read(document_position, self.regularDataSize)
        elif role == self.DataSizeRole:
            return self.regularDataSize

    def indexFlags(self, index):
        flags = self.FlagEditable
        if index > self.lastRealIndex:
            flags |= self.FlagVirtual
        elif self.document is not None and self.document.isRangeModified(index.data(self.DocumentPositionRole),
                                                                     self.regularDataSize):
            flags |= self.FlagModified
        return flags

    def headerData(self, section, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and 0 <= section < self.regularColumnCount:
            return formatters.IntegerFormatter(base=16).format(section * self.regularDataSize)

    def _onDocumentDataChanged(self, start, length):
        length = length if length >= 0 else self.document.length - start
        self.dataChanged.emit(self.indexFromPosition(start), self.indexFromPosition(start + length - 1))

    def _onDocumentDataResized(self, new_size):
        self.dataResized.emit(self.lastRealIndex)

    @property
    def regular(self):
        return True

    def delegateForIndex(self, index):
        if not self.document.readOnly and index.flags & self.FlagEditable:
            return self._delegateType(index, is_inserted=False, insert_mode=self.defaultInsertMode)

    def delegateForNewIndex(self, input_text, before_index):
        if not self.document.readOnly and not self.document.fixedSize:
            data_to_insert, index_text, cursor_offset = self._dataForNewIndex(input_text, before_index)
            position = before_index.data(self.DocumentPositionRole) if before_index else self.document.length
            if data_to_insert and position >= 0:
                # note that length of inserted data can differ from regular data size, it is normal
                if isinstance(data_to_insert, str):
                    data_to_insert = bytes(data_to_insert, encoding='latin')
                self.document.insertSpan(position, documents.DataSpan(data_to_insert))
                new_index = self.indexFromPosition(position)
                return self._delegateType(new_index, is_inserted=True, init_text=index_text,
                                          cursor_offset=cursor_offset, insert_mode=self.defaultInsertMode)

    @property
    def defaultInsertMode(self) -> bool:
        """Return insert mode that should be used for index delegate created by delegateForIndex
        and delagateForNewIndex default implementations.
        """
        raise NotImplementedError()

    def _dataForNewIndex(self, input_text, before_index) -> (bytes, str, int):
        """Return tuple (data, index_text, cursor_offset) for index that will be created by default
        delegateForNewIndex implementation. First tuple element is binary data that will be inserted, second
        is initial editing index text, and third is offset from beginning of text where cursor will be positioned
        before editing.
        """
        raise NotImplementedError()

    def _onDocumentBytesRemoved(self, position, length):
        if position == 0:
            start_index = ModelIndex()
        else:
            start_index = self.indexFromPosition(position - 1)
        self.indexesRemoved.emit(start_index, length // self.regularDataSize)

    def _onDocumentBytesInserted(self, position, length):
        start_index = self.indexFromPosition(position)
        if start_index:
            self.indexesInserted.emit(start_index, length // self.regularDataSize)

    def indexOffset(self, index):
        if index and index.model is self:
            return index.row * self.regularColumnCount + index.column
        return -1

    def indexFromOffset(self, offset):
        return self.indexFromPosition(self.regularDataSize * offset)


class RegularValueColumnModel(RegularColumnModel):
    """Specialization of RegularColumnModel that uses valuecodecs to get data for indexes.
    """

    def __init__(self, document, valuecodec, formatter, columns_on_row=16, delegate_type=StandardEditDelegate):
        self.valuecodec = valuecodec
        self.formatter = formatter
        self.columnsOnRow = columns_on_row
        RegularColumnModel.__init__(self, document, delegate_type=delegate_type)

    @property
    def regularDataSize(self):
        return self.valuecodec.dataSize

    @property
    def regularColumnCount(self):
        return self.columnsOnRow

    def textForDocumentData(self, document_data, index, role=Qt.DisplayRole):
        try:
            decoded = self.valuecodec.decode(document_data)
        except struct.error:
            return '!' * self.regularTextLength if self.regularTextLength > 0 else '!'
        return self.formatter.format(decoded)

    def _saveData(self, delegate):
        if delegate.index and delegate.index.model is self:
            position = delegate.index.documentPosition
            if position is None or position < 0:
                raise ValueError('invalid position for index resolved')

            try:
                raw_data = self.valuecodec.encode(self.formatter.parse(delegate.data(Qt.EditRole)))
            except (ValueError, struct.error, OverflowError):
                return False
            current_data = delegate.index.documentData if not delegate.index.virtual else b''

            if isinstance(raw_data, str):
                raw_data = bytes(raw_data, encoding='latin')

            if raw_data != current_data:
                self.document.writeSpan(position, documents.DataSpan(raw_data))
            return True


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

    frameScrolled = pyqtSignal(object, object)  # first argument is new first frame row, second one is old first frame row
    frameResized = pyqtSignal(int, int)  # first argument is new frame size, second one is old frame size
    rowsUpdated = pyqtSignal(int, int)  # first argument is first modified frame row, second one is number of modified rows
                                # signal is emitted for rows that has been modified (and not emitted when frame scrolled)

    def __init__(self, source_model):
        AbstractModel.__init__(self)
        self._firstRow = 0
        self._rowCount = 0
        self._lastSourceIndex = source_model.lastRealIndex
        self._activeDelegate = None
        self.sourceModel = source_model
        self.sourceModel.dataChanged.connect(self._onDataChanged)
        self.sourceModel.dataResized.connect(self._onDataResized)
        self.sourceModel.modelReset.connect(self._onModelResetted)

    @property
    def activeDelegate(self):
        return self._activeDelegate

    @activeDelegate.setter
    def activeDelegate(self, new_delegate):
        if new_delegate is not self._activeDelegate:
            if self._activeDelegate is not None:
                self._activeDelegate.dataChanged.disconnect(self._onDelegateUpdated)
                self._activeDelegate.finished.disconnect(self._onDelegateFinished)

            if self._activeDelegate is not None:
                del_index = self.toFrameIndex(self._activeDelegate.index)
                if del_index:
                    self._onDataChanged(del_index, del_index)

            self._activeDelegate = new_delegate

            if new_delegate is not None:
                new_delegate.dataChanged.connect(self._onDelegateUpdated)
                new_delegate.finished.connect(self._onDelegateFinished)

                self._onDelegateUpdated()

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
        if self._activeDelegate is not None and self._activeDelegate.index == self.toSourceIndex(index):
            return self._activeDelegate.data(role)
        else:
            return self.sourceModel.indexData(self.toSourceIndex(index), role)

    def indexFlags(self, index):
        if self._activeDelegate is not None and self._activeDelegate.index == self.toSourceIndex(index):
            return self._activeDelegate.flags
        else:
            return self.sourceModel.indexFlags(self.toSourceIndex(index))

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
        first_row = max(self._firstRow, first_index.row)
        row_count = max(0, min(last_index.row - first_row + 1, self._rowCount + self._firstRow - first_row))
        self.rowsUpdated.emit(first_row - self._firstRow, row_count)

    def _onDataResized(self, new_last_index):
        # as number of rows will not be affected, the only thing this can cause is updating some indexes.
        if not new_last_index:
            # boundary case: model was cleared
            first_model_row = 0
            if not self._lastSourceIndex:
                # our frame was empty and will stay empty too: no need to do any updates
                return
            last_model_row = self._lastSourceIndex.row
        elif not self._lastSourceIndex:
            if new_last_index.row < self._firstRow:
                return
            first_model_row = self._firstRow
            last_model_row = new_last_index.row
        else:
            first_model_row = min(self._lastSourceIndex.row, new_last_index.row)
            last_model_row = max(self._lastSourceIndex.row, new_last_index.row)

        self._lastSourceIndex = new_last_index

        # now determine range of rows that we should update
        if last_model_row < self._firstRow or first_model_row >= self._firstRow + self._rowCount:
            return

        first_model_row = max(self._firstRow, first_model_row)
        last_model_row = min(self._firstRow + self._rowCount - 1, last_model_row)

        self.rowsUpdated.emit(first_model_row - self._firstRow, last_model_row - first_model_row + 1)

    def _onModelResetted(self):
        self.rowsUpdated.emit(0, self._rowCount)

    def _onDelegateUpdated(self):
        if self._activeDelegate is not None:
            index = self._activeDelegate.index
            frame_index = self.toFrameIndex(index)
            if frame_index:
                self._onDataChanged(index, index)

    def _onDelegateFinished(self):
        delegate = self._activeDelegate
        self.activeDelegate = None
        if delegate is not None:
            frame_index = self.toFrameIndex(delegate.index)
            if frame_index:
                self._onDataChanged(delegate.index, delegate.index)
