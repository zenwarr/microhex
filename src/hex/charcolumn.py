from PyQt4.QtGui import QRawFont, QFont, QValidator, QWidget, QComboBox, QFormLayout, QSpinBox, QSizePolicy
from PyQt4.QtCore import Qt
import hex.hexwidget as hexwidget
import hex.encodings as encodings
import hex.editor as editor
import hex.columnproviders as columnproviders
import hex.utils as utils


class CharColumnModel(hexwidget.ColumnModel):
    """This column displays data as characters in one of possible encodings.
    """

    ReplacementCharacter = '·'

    def __init__(self, editor, codec, render_font, bytes_on_row=16):
        hexwidget.ColumnModel.__init__(self, editor)

        self.codec = codec
        self.bytesOnRow = bytes_on_row
        self._renderFont = QRawFont.fromFont(render_font)
        self._rowCount = 0
        self._editingIndex = None
        self.reset()

    @property
    def regularCellDataSize(self):
        return self.codec.unitSize

    @property
    def regularColumnCount(self):
        return self.bytesOnRow // self.codec.unitSize

    def reset(self):
        # number of bytes on row should be multiplier of codec.unitSize
        if self.bytesOnRow % self.codec.unitSize:
            raise ValueError('number of bytes on row should be multiplier of encoding unit size')
        self._updateRowCount()
        hexwidget.ColumnModel.reset(self)

    @property
    def renderFont(self):
        return self._renderFont

    @renderFont.setter
    def renderFont(self, new_font):
        if isinstance(new_font, QFont):
            new_font = QRawFont.fromFont(new_font)
        self._renderFont = new_font
        self.modelReset.emit()

    def _updateRowCount(self):
        self._rowCount = len(self.editor) // self.bytesOnRow + bool(len(self.editor) % self.bytesOnRow)

    def rowCount(self):
        return -1

    def columnCount(self, row):
        return self.bytesOnRow // self.codec.unitSize if row >= 0 else -1

    def realRowCount(self):
        return self._rowCount

    def realColumnCount(self, row):
        if row < 0:
            return -1
        position = row * self.bytesOnRow
        if position >= len(self.editor):
            return 0
        elif row + 1 == self._rowCount:
            bytes_left = len(self.editor) % self.bytesOnRow
            if not bytes_left:
                return self.bytesOnRow // self.codec.unitSize
            else:
                return bytes_left // self.codec.unitSize + bool(bytes_left % self.codec.unitSize)
        else:
            return self.bytesOnRow // self.codec.unitSize

    def indexFromPosition(self, position):
        return self.index(position // self.bytesOnRow,
                         (position % self.bytesOnRow) // self.codec.unitSize)

    def indexData(self, index, role=Qt.DisplayRole):
        if not index or self.editor is None:
            return None

        position = index.row * self.bytesOnRow + index.column * self.codec.unitSize
        is_virtual = position >= len(self.editor)

        if role == self.EditorPositionRole:
            return position
        elif role == self.DataSizeRole:
            return self.codec.unitSize
        elif role == self.EditorDataRole:
            return bytes() if is_virtual else self.editor.read(position, self.codec.unitSize)
        elif role in (Qt.DisplayRole, Qt.EditRole):
            if is_virtual:
                return '.' if role == Qt.DisplayRole else ''
            try:
                char_data = self.codec.getCharacterData(self.editor, position)
                if char_data.startPosition != position:
                    return ' '
                else:
                    return char_data.unicode if role == Qt.EditRole else self._translateToVisualCharacter(char_data.unicode)
            except encodings.EncodingError:
                return '!' if role == Qt.DisplayRole else ''
        return None

    def indexFlags(self, index):
        flags = self.FlagEditable
        if not self.lastRealIndex or (index.row + 1 >= self.realRowCount() and index > self.lastRealIndex):
            flags |= self.FlagVirtual
        else:
            if self.editor.isRangeModified(index.data(self.EditorPositionRole), index.data(self.DataSizeRole)):
                flags |= self.FlagModified

            try:
                d = self.codec.getCharacterData(self.editor, index.data(self.EditorPositionRole))
            except encodings.EncodingError:
                flags |= self.FlagBroken
        return flags

    def beginEditIndex(self, index):
        if index:
            hexwidget.ColumnModel.beginEditIndex(self, index)
            return True, False
        return False, False

    def beginEditNewIndex(self, input_text, before_index):
        if not self.editor.fixedSize:
            if input_text:
                if self.createValidator().validate(input_text[0], 1)[0] == QValidator.Invalid:
                    return hexwidget.ModelIndex(), -1, False
                data_to_insert = self.codec.encodeString(input_text[0])
            else:
                data_to_insert = self.codec.encodeString('\x00')

            position = self.indexData(before_index, self.EditorPositionRole)
            self.editor.insertSpan(position, editor.DataSpan(self.editor, data_to_insert))

            new_index = self.indexFromPosition(position)
            hexwidget.ColumnModel.beginEditIndex(self, new_index)
            return new_index, 1, False
        return hexwidget.ModelIndex(), -1, False

    def setIndexData(self, index, value, role=Qt.EditRole):
        if not self.editingIndex or self.editingIndex != index or role != Qt.EditRole:
            raise RuntimeError()

        if role == Qt.EditRole:
            position = self.indexData(index, self.EditorPositionRole)
            if position is None or position < 0:
                raise ValueError('invalid position for index resolved')

            raw_data = self.codec.encodeString(value)
            current_data = self.indexData(index, self.EditorDataRole)

            if raw_data == current_data:
                return

            self.editor.writeSpan(position, editor.DataSpan(self.editor, raw_data))
        else:
            raise ValueError('data for given role is not writeable')

    def nextEditableIndex(self, from_index):
        if not from_index:
            return hexwidget.ModelIndex()

        position = self.indexData(from_index, self.EditorPositionRole)
        try:
            char_data = self.codec.getCharacterData(self.editor, position)
        except encodings.EncodingError:
            return from_index.next

        if char_data.startPosition != position:
            return from_index.next
        else:
            return self.indexFromPosition(position + char_data.bytesCount)

    def previousEditableIndex(self, from_index):
        if not from_index:
            prev_char_byte = len(self.editor)
        else:
            try:
                position = self.codec.findCharacterStart(self.editor, from_index.data(self.EditorPositionRole))
                if position <= 0:
                    return hexwidget.ModelIndex()
                elif position != from_index.data(self.EditorPositionRole):
                    return from_index.previous
            except encodings.EncodingError:
                return from_index.previous
            prev_char_byte = position - 1

        try:
            character_start = self.codec.findCharacterStart(self.editor, prev_char_byte)
            return self.indexFromPosition(character_start)
        except encodings.EncodingError:
            return self.indexFromPosition(prev_char_byte)

    def _translateToVisualCharacter(self, text):
        import unicodedata

        result = ''
        for char in text:
            if unicodedata.category(char) in ('Cc', 'Cf', 'Cn', 'Co', 'Cs', 'Lm', 'Mc', 'Zl', 'Zp'):
                result += self.ReplacementCharacter
            elif not self._renderFont.supportsCharacter(char):
                result += self.ReplacementCharacter
            else:
                result += char
        return result

    @property
    def preferSpaced(self):
        return False

    @property
    def regular(self):
        return True

    def _onEditorDataChanged(self, start, length):
        length = length if length >= 0 else len(self.editor) - start
        self.dataChanged.emit(self.indexFromPosition(start), self.indexFromPosition(start + length - 1))

    def _onEditorDataResized(self, new_size):
        self._updateRowCount()
        self.dataResized.emit(self.lastRealIndex)

    def createValidator(self):
        return CharColumnValidator(self.codec)


class CharColumnValidator(QValidator):
    def __init__(self, codec):
        QValidator.__init__(self)
        self.codec = codec

    def validate(self, text, cursor_pos, original_text=None):
        if not text:
            return self.Intermediate, text, None
        return (self.Acceptable if self.codec.canEncode(text) and len(text) == 1 else self.Invalid), text, None


class CharColumnProvider(columnproviders.AbstractColumnProvider):
    def __init__(self):
        columnproviders.AbstractColumnProvider.__init__(self)
        self.name = utils.tr('Character column')
        self.columnModelType = CharColumnModel

    def createConfigurationWidget(self, parent, hex_widget, column=None):
        return CharColumnConfigurationWidget(parent, hex_widget, column)


class CharColumnConfigurationWidget(QWidget, columnproviders.AbstractColumnConfigurationWidget):
    def __init__(self, parent, hex_widget, column):
        QWidget.__init__(self, parent)
        columnproviders.AbstractColumnConfigurationWidget.__init__(self)
        self.hexWidget = hex_widget
        self.columnModel = column

        self.setLayout(QFormLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.cmbEncoding = QComboBox(self)
        self.cmbEncoding.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.layout().addRow(utils.tr('Encoding:'), self.cmbEncoding)
        for encoding in sorted(encodings.encodings.keys()):
            self.cmbEncoding.addItem(encoding)
            if column is not None and column.codec.name == encoding:
                self.cmbEncoding.setCurrentIndex(self.cmbEncoding.count() - 1)
        if column is None:
            self.cmbEncoding.setCurrentIndex(self.cmbEncoding.findText('Windows-1251'))

        self.spnBytesOnRow = QSpinBox(self)
        self.spnBytesOnRow.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.spnBytesOnRow.setMinimum(1)
        self.spnBytesOnRow.setMaximum(32)
        self.layout().addRow(utils.tr('Bytes on row:'), self.spnBytesOnRow)
        if column is not None:
            self.spnBytesOnRow.setValue(column.bytesOnRow)
        else:
            self.spnBytesOnRow.setValue(16)

    def createColumnModel(self, hex_widget):
        model = CharColumnModel(self.hexWidget.editor, encodings.getCodec(self.cmbEncoding.currentText()),
                                self.hexWidget.font(), self.spnBytesOnRow.value())
        return model

    def saveToColumn(self, column):
        column.codec = encodings.getCodec(self.cmbEncoding.currentText())
        column.bytesOnRow = self.spnBytesOnRow.value()
        column.reset()
