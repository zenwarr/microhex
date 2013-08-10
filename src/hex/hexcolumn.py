from PyQt4.QtCore import Qt
from PyQt4.QtGui import QValidator, QWidget, QFormLayout, QComboBox, QCheckBox, QSpinBox, QSizePolicy
import hex.hexwidget as hexwidget
import hex.columnproviders as columnproviders
import hex.utils as utils
import hex.valuecodecs as valuecodecs
import hex.formatters as formatters


class HexColumnModel(hexwidget.RegularValueColumnModel):
    """Standart column for hex-editors. Displays data as numbers. This model is regular (has equal number of
    columns in each row, except last one) and infinite (supports virtual indexes).
    """
    def __init__(self, document, valuecodec, formatter, columns_on_row=16):
        self._cellTextSize = 0
        hexwidget.RegularValueColumnModel.__init__(self, document, valuecodec or valuecodecs.IntegerCodec(),
                                                   formatter or formatters.IntegerFormatter(), columns_on_row)

    def virtualIndexData(self, index, role=Qt.DisplayRole):
        if role == Qt.EditRole:
            return self.textForDocumentData(b'\x00' * self.regularCellDataSize, index, Qt.EditRole)
        return hexwidget.RegularValueColumnModel.virtualIndexData(self, index, role)

    @property
    def regularCellTextLength(self):
        return self._cellTextSize

    def reset(self):
        min_value, max_value = self.valuecodec.minimal, self.valuecodec.maximal
        self._cellTextSize = max(len(self.formatter.format(min_value)), len(self.formatter.format(max_value)))
        hexwidget.RegularValueColumnModel.reset(self)

    @property
    def preferSpaced(self):
        return True

    def createValidator(self):
        return HexColumnValidator(self.formatter, self.valuecodec)

    def indexData(self, index, role=Qt.DisplayRole):
        data = hexwidget.RegularValueColumnModel.indexData(self, index, role)
        if data is not None:
            if role == Qt.DisplayRole and index != self.editingIndex:
                return ' ' * (self._cellTextSize - len(data)) + data
            elif role == Qt.EditRole or (role == Qt.DisplayRole and index == self.editingIndex):
                if self.valuecodec.signed and not data.startswith('-') and not data.startswith('+'):
                    return '+' + data
        return data

    def _dataForNewIndex(self, input_text, before_index):
        if input_text in ('-', '+'):
            if self.valuecodec.signed:
                text = input_text + self.formatter.format(0)
                cursor_pos = 1
            else:
                return None, '', -1
        else:
            zero_count = self._cellTextSize - len(input_text)
            while zero_count > 0:
                text = ('+' * self.valuecodec.signed) + input_text + '0' * zero_count
                if self.createValidator().validate(text, len(input_text) + self.valuecodec.signed)[0] != QValidator.Invalid:
                    break
                zero_count -= 1
            else:
                return None, '', -1
            cursor_pos = len(input_text) + self.valuecodec.signed

        if self.createValidator().validate(text, len(input_text))[0] != QValidator.Invalid:
            import struct
            try:
                return self.valuecodec.encode(self.formatter.parse(text)), text, cursor_pos
            except (ValueError, struct.error):
                pass

        return None, '', -1

    @property
    def defaultCellInsertMode(self):
        return False


class HexColumnValidator(QValidator):
    def __init__(self, formatter, codec):
        QValidator.__init__(self)
        self.formatter = formatter
        self.codec = codec

    def validate(self, text, cursor_pos, original_text=None):
        import struct

        if not text:
            return self.Intermediate, text, cursor_pos
        elif self.codec.signed and original_text is not None and cursor_pos == 0 and text[0] not in '-+':
            text = original_text[0] + text[0] + text[2:]
            cursor_pos = 2
        else:
            cursor_pos = None

        r1 = self.formatter.validate(text)
        if r1 == self.Acceptable:
            try:
                self.codec.encode(self.formatter.parse(text))
                return r1, text, cursor_pos
            except struct.error:
                return self.Invalid, text, cursor_pos
        return r1, text, cursor_pos


class HexColumnProvider(columnproviders.AbstractColumnProvider):
    def __init__(self):
        columnproviders.AbstractColumnProvider.__init__(self)
        self.name = utils.tr('Integer column')
        self.columnModelType = HexColumnModel

    def createConfigurationWidget(self, parent, hex_widget, column=None):
        return HexColumnConfigurationWidget(parent, hex_widget, column)


class HexColumnConfigurationWidget(QWidget, columnproviders.AbstractColumnConfigurationWidget):
    def __init__(self, parent, hex_widget, column):
        QWidget.__init__(self, parent)
        columnproviders.AbstractColumnConfigurationWidget.__init__(self)
        self.hexWidget = hex_widget
        self.column = column

        self.setLayout(QFormLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.cmbBinaryFormat = QComboBox(self)
        self.cmbBinaryFormat.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.layout().addRow(utils.tr('Binary format:'), self.cmbBinaryFormat)
        self.cmbBinaryFormat.currentIndexChanged[int].connect(self._onBinaryFormatChanged)

        self.chkSigned = QCheckBox()
        self.layout().addRow(utils.tr('Signed values:'), self.chkSigned)
        if column is not None:
            self.chkSigned.setChecked(column.valuecodec.signed)

        self.cmbEndianess = QComboBox(self)
        self.cmbEndianess.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.layout().addRow(utils.tr('Endianess:'), self.cmbEndianess)
        self.cmbEndianess.addItem(utils.tr('Little endian'), valuecodecs.LittleEndian)
        self.cmbEndianess.addItem(utils.tr('Big endian'), valuecodecs.BigEndian)
        if column is not None:
            self.cmbEndianess.setCurrentIndex(self.cmbEndianess.findData(column.valuecodec.endianess))
        else:
            self.cmbEndianess.setCurrentIndex(0)

        icodec = valuecodecs.IntegerCodec
        for fmt in (icodec.Format8Bit, icodec.Format16Bit, icodec.Format32Bit, icodec.Format64Bit):
            self.cmbBinaryFormat.addItem(icodec.formatName(fmt), fmt)
            if column is not None and column.valuecodec.binaryFormat == fmt:
                self.cmbBinaryFormat.setCurrentIndex(self.cmbBinaryFormat.count() - 1)
        if column is None:
            self.cmbBinaryFormat.setCurrentIndex(0)

        self.cmbBase = QComboBox(self)
        self.cmbBase.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.layout().addRow(utils.tr('Base:'), self.cmbBase)
        for base in ((utils.tr('Hex'), 16), (utils.tr('Dec'), 10), (utils.tr('Oct'), 8), (utils.tr('Bin'), 2)):
            self.cmbBase.addItem(base[0], base[1])
        if column is not None:
            self.cmbBase.setCurrentIndex(self.cmbBase.findData(column.formatter.base))

        self.spnColumnsOnRow = QSpinBox(self)
        self.spnColumnsOnRow.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.spnColumnsOnRow.setMinimum(1)
        self.spnColumnsOnRow.setMaximum(32)
        self.layout().addRow(utils.tr('Columns on row:'), self.spnColumnsOnRow)
        if column is not None:
            self.spnColumnsOnRow.setValue(column.columnsOnRow)
        else:
            self.spnColumnsOnRow.setValue(16)

    def _onBinaryFormatChanged(self, index):
        self.cmbEndianess.setEnabled(self.cmbBinaryFormat.itemData(index) != valuecodecs.IntegerCodec.Format8Bit)

    @property
    def _valueCodec(self):
        valuecodec = valuecodecs.IntegerCodec()
        valuecodec.binaryFormat = self.cmbBinaryFormat.itemData(self.cmbBinaryFormat.currentIndex())
        valuecodec.signed = self.chkSigned.isChecked()
        valuecodec.endianess = self.cmbEndianess.itemData(self.cmbEndianess.currentIndex())
        return valuecodec

    @property
    def _formatter(self):
        valuecodec = self._valueCodec
        formatter = formatters.IntegerFormatter()
        formatter.base = self.cmbBase.itemData(self.cmbBase.currentIndex())
        maximal = formatter.format(valuecodec.maximal)
        minimal = formatter.format(valuecodec.minimal)
        if minimal.startswith('-'):
            minimal = minimal[1:]
        formatter.padding = max(len(maximal), len(minimal))
        return formatter

    def createColumnModel(self, hex_widget):
        return HexColumnModel(hex_widget.document, self._valueCodec, self._formatter, self.spnColumnsOnRow.value())

    def saveToColumn(self, column):
        column.valuecodec = self._valueCodec
        column.formatter = self._formatter
        column.columnsOnRow = self.spnColumnsOnRow.value()
        column.reset()
