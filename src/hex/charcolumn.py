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
        self.reset()

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
            if is_virtual:
                return self.codec.unitSize
            try:
                return self.codec.getCharacterSize(self.editor, position)
            except encodings.EncodingError:
                return 1
        elif role == self.EditorDataRole:
            if is_virtual:
                return bytes()
            try:
                return self.editor.readAtEnd(self.codec.findCharacterStart(self.editor, position),
                                         self.codec.getCharacterSize(self.editor, position))
            except encodings.EncodingError:
                return self.editor.readAtEnd(position, 1)
        elif role in (Qt.DisplayRole, Qt.EditRole):
            if is_virtual:
                return '.' if role == Qt.DisplayRole else ''
            try:
                character_start = self.codec.findCharacterStart(self.editor, position)
                if character_start != position:
                    return ' '
                else:
                    decoded = self.codec.decodeCharacter(self.editor, position)
                    return decoded if role == Qt.EditRole else self._translateToVisualCharacter(decoded)
            except encodings.EncodingError:
                return '!' if role == Qt.DisplayRole else ''
        return None

    def indexFlags(self, index):
        flags = self.FlagEditable
        if not self.lastRealIndex or (index.row + 1 >= self.realRowCount() and index > self.lastRealIndex):
            flags |= self.FlagVirtual
        elif self.editor.isRangeModified(index.data(self.EditorPositionRole), index.data(self.DataSizeRole)):
            flags |= self.FlagModified
        return flags

    def setIndexData(self, index, value, role=Qt.EditRole):
        if not index or index.model is not self:
            raise ValueError('invalid index')

        if role == Qt.EditRole:
            position = self.indexData(index, self.EditorPositionRole)
            if position is None or position < 0:
                raise ValueError('invalid position for index resolved')

            raw_data = self.codec.encodeString(value)
            current_data = self.indexData(index, self.EditorDataRole)

            if raw_data == current_data:
                return

            data_span = editor.DataSpan(self.editor, raw_data)
            if len(current_data) == len(raw_data):
                self.editor.writeSpan(position, data_span)
            else:
                self.editor.beginComplexAction()
                try:
                    self.editor.remove(position, len(current_data))
                    self.editor.insertSpan(position, editor.DataSpan(self.editor, raw_data))
                finally:
                    self.editor.endComplexAction()
        else:
            raise ValueError('data for given role is not writeable')

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

    def onEditorDataChanged(self, start, length):
        length = length if length >= 0 else len(self.editor) - start
        self.dataChanged.emit(self.indexFromPosition(start), self.indexFromPosition(start + length - 1))

    def onEditorDataResized(self, new_size):
        self._updateRowCount()
        self.dataResized.emit(self.lastRealIndex)

    def defaultIndexData(self, before_index, role=Qt.EditRole):
        if before_index:
            if role == Qt.EditRole:
                return '\x00'
            elif role == self.EditorDataRole:
                return self.codec.encodeString('\x00')

    def createValidator(self):
        return CharColumnValidator(self.codec)


class CharColumnValidator(QValidator):
    def __init__(self, codec):
        QValidator.__init__(self)
        self.codec = codec

    def validate(self, text):
        if not text:
            return self.Intermediate
        return self.Acceptable if self.codec.canEncode(text) and len(text) == 1 else self.Invalid


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
