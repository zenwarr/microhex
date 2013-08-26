from PyQt4.QtGui import QRawFont, QFont, QValidator, QWidget, QComboBox, QFormLayout, QSpinBox, QSizePolicy
from PyQt4.QtCore import Qt
import unicodedata
import hex.models as models
import hex.encodings as encodings
import hex.columnproviders as columnproviders
import hex.utils as utils
import hex.documents as documents


blocked_categories = ('Cc', 'Cf', 'Cn', 'Co', 'Cs', 'Lm', 'Mc', 'Zl', 'Zp')


class CharColumnModel(models.RegularColumnModel):
    """This column displays data as characters in one of possible encodings.
    """

    ReplacementCharacter = '·'

    def __init__(self, document, codec, render_font, bytes_on_row=16):
        self.codec = codec
        self._bytesOnRow = bytes_on_row
        self._renderFont = QRawFont.fromFont(render_font)
        models.RegularColumnModel.__init__(self, document, delegate_type=CharColumnEditDelegate)
        self.reset()

    @property
    def regularDataSize(self):
        return self.codec.unitSize

    @property
    def regularColumnCount(self):
        return self._bytesOnRow // self.codec.unitSize

    @property
    def defaultInsertMode(self):
        return False

    def reset(self):
        # number of bytes on row should be multiplier of codec.unitSize
        if self._bytesOnRow % self.codec.unitSize:
            raise ValueError('number of bytes on row should be multiplier of encoding unit size')
        models.ColumnModel.reset(self)

    @property
    def renderFont(self):
        return self._renderFont

    @renderFont.setter
    def renderFont(self, new_font):
        if isinstance(new_font, QFont):
            new_font = QRawFont.fromFont(new_font)
        self._renderFont = new_font
        self.reset()

    def textForDocumentData(self, document_data, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole or role == Qt.EditRole:
            try:
                position = index.documentPosition
                char_data = self.codec.getCharacterData(self.document, position)
                if char_data.startPosition != position:
                    return ' '
                else:
                    return self._translateToVisualCharacter(char_data.unicode)
            except encodings.EncodingError:
                return '!' if role == Qt.DisplayRole else self.ReplacementCharacter

    def indexFlags(self, index):
        flags = models.RegularColumnModel.indexFlags(self, index)
        try:
            self.codec.getCharacterData(self.document, index.documentPosition)
        except encodings.EncodingError:
            flags |= self.FlagBroken
        return flags

    def _dataForNewIndex(self, input_text, before_index):
        # check if input is correct
        if input_text:
            if self.createValidator().validate(input_text[0], 1) != QValidator.Acceptable:
                return b'', '', -1
            data_to_insert = self.codec.encodeString(input_text[0])
        else:
            data_to_insert = self.codec.encodeString('\x00')

        return data_to_insert, input_text[0], 1

    def _saveData(self, delegate):
        position = delegate.index.documentPosition
        if position is None or position < 0:
            raise ValueError('invalid position for index resolved')
        raw_data = self.codec.encodeString(delegate.data(Qt.EditRole))
        current_data = delegate.index.documentData
        if isinstance(raw_data, str):
            raw_data = bytes(raw_data, encoding='latin')
        if raw_data != current_data:
            self.document.writeSpan(position, documents.DataSpan(raw_data))

    def _translateToVisualCharacter(self, text):
        result = ''
        for char in text:
            if unicodedata.category(char) in blocked_categories:
                result += self.ReplacementCharacter
            elif not self._renderFont.supportsCharacter(char):
                result += self.ReplacementCharacter
            else:
                result += char
        return result

    @property
    def preferSpaced(self):
        return False

    def createValidator(self):
        return CharColumnValidator(self.codec)

    def parseTextInput(self, text):
        try:
            return self.codec.encodeString(text)
        except encodings.EncodingError:
            return b''


class CharColumnEditDelegate(models.StandardEditDelegate):
    @property
    def nextEditIndex(self):
        if not self.index:
            return models.ModelIndex()

        codec = self.index.model.codec
        document = self.index.model.document
        position = self.index.documentPosition
        try:
            char_data = codec.getCharacterData(document, position)
        except encodings.EncodingError:
            return self.index.next

        if char_data.startPosition != position:
            return self.index.next
        else:
            return self.index.model.indexFromPosition(position + char_data.bytesCount)

    @property
    def previousEditIndex(self):
        if not self.index:
            return models.ModelIndex()

        codec = self.index.model.codec
        document = self.index.model.document
        try:
            position = codec.findCharacterStart(document, self.index.documentPosition)
            if position <= 0:
                return models.ModelIndex()
            elif position != self.index.documentPosition:
                return self.index.previous
        except encodings.EncodingError:
            return self.index.previous
        prev_char_byte = position - 1

        try:
            character_start = codec.findCharacterStart(document, prev_char_byte)
            return self.index.model.indexFromPosition(character_start)
        except encodings.EncodingError:
            return self.index.model.indexFromPosition(prev_char_byte)


class CharColumnValidator(QValidator):
    def __init__(self, codec):
        QValidator.__init__(self)
        self.codec = codec

    def validate(self, text, cursor_pos):
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
            if column is not None and column.codec.name.lower() == encoding.lower():
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
        model = CharColumnModel(self.hexWidget.document, encodings.getCodec(self.cmbEncoding.currentText()),
                                self.hexWidget.font(), self.spnBytesOnRow.value())
        return model

    def saveToColumn(self, column):
        column.codec = encodings.getCodec(self.cmbEncoding.currentText())
        column._bytesOnRow = self.spnBytesOnRow.value()
        column.reset()
