from PyQt4.QtCore import Qt
from PyQt4.QtGui import QValidator, QWidget, QFormLayout, QComboBox, QCheckBox, QSpinBox, QSizePolicy
import hex.hexwidget as hexwidget
import hex.editor as editor
import hex.columnproviders as columnproviders
import hex.utils as utils
import hex.valuecodecs as valuecodecs
import hex.formatters as formatters
import struct


class HexColumnModel(hexwidget.ColumnModel):
    """Standart column for hex-editors. Displays data as numbers. This model is regular (has equal number of
    columns in each row, except last one) and infinite (supports virtual indexes).
    """

    def __init__(self, editor, valuecodec, formatter, columns_on_row=16):
        hexwidget.ColumnModel.__init__(self, editor)
        self.valuecodec = valuecodec
        self.formatter = formatter
        self.columnsOnRow = columns_on_row
        self.reset()

    def reset(self):
        self._rowCount = 0
        self._bytesOnRow = self.columnsOnRow * self.valuecodec.dataSize
        min_value, max_value = self.valuecodec.minimal, self.valuecodec.maximal
        self._cellTextSize = max(len(self.formatter.format(min_value)), len(self.formatter.format(max_value)))
        self._updateRowCount()
        hexwidget.ColumnModel.reset(self)

    def rowCount(self):
        return -1

    def columnCount(self, row):
        return self.columnsOnRow

    def realRowCount(self):
        return self._rowCount

    def realColumnCount(self, row):
        if row + 1 == self._rowCount:
            count = (len(self.editor) % self.bytesOnRow) // self.valuecodec.dataSize
            return count or self.columnsOnRow
        elif row >= self._rowCount:
            return 0
        return self.columnsOnRow

    def indexFromPosition(self, editor_position):
        return self.index(int(editor_position // self.bytesOnRow),
                          int(editor_position % self.bytesOnRow) // self.valuecodec.dataSize)

    def indexData(self, index, role=Qt.DisplayRole):
        if not index or self.editor is None:
            return None
        editor_position = self.bytesOnRow * index.row + self.valuecodec.dataSize * index.column

        if role == Qt.DisplayRole or role == Qt.EditRole:
            if editor_position >= len(self.editor):
                return ('.' if role == Qt.DisplayRole else '0') * self._cellTextSize
            else:
                editor_data = self.editor.readAtEnd(editor_position, self.valuecodec.dataSize)
                try:
                    decoded = self.valuecodec.decode(editor_data)
                except struct.error:
                    return '!' * self._cellTextSize
                return self.formatter.format(decoded)
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

    def setIndexData(self, index, value, role=Qt.EditRole):
        if not index or index.model is not self:
            raise ValueError('invalid index')

        position = self.indexData(index, self.EditorPositionRole)
        if position is None or position < 0:
            raise ValueError('invalid position for index resolved')

        raw_data = self.valuecodec.encode(self.formatter.parse(value))
        current_data = self.indexData(index, self.EditorDataRole)

        if raw_data == current_data:
            return

        self.editor.writeSpan(position, editor.DataSpan(self.editor, raw_data))

    def indexFlags(self, index):
        flags = hexwidget.ColumnModel.FlagEditable
        if index.row >= self._rowCount or (index.row == self._rowCount - 1 and index > self.lastRealIndex):
            flags |= hexwidget.ColumnModel.FlagVirtual
        elif self.editor is not None and self.editor.isRangeModified(index.data(self.EditorPositionRole),
                                                                   index.data(self.DataSizeRole)):
            flags |= hexwidget.ColumnModel.FlagModified
        return flags

    @property
    def bytesOnRow(self):
        return self._bytesOnRow

    def onEditorDataChanged(self, start, length):
        length = length if length >= 0 else len(self.editor) - start
        self.dataChanged.emit(self.indexFromPosition(start), self.indexFromPosition(start + length - 1))

    def onEditorDataResized(self, new_size):
        self._updateRowCount()
        self.dataResized.emit(self.lastRealIndex)

    @property
    def preferSpaced(self):
        return True

    @property
    def regular(self):
        return True

    def _updateRowCount(self):
        self._rowCount = len(self.editor) // self.bytesOnRow + bool(len(self.editor) % self.bytesOnRow)

    def insertDefaultIndex(self, before_index):
        pos = before_index.data(self.EditorPositionRole)
        self.editor.insertSpan(pos, editor.FillSpan(self.editor, b'\x00', self.valuecodec.dataSize))

    def createValidator(self):
        return HexColumnValidator(self.formatter, self.valuecodec)


class HexColumnValidator(QValidator):
    def __init__(self, formatter, codec):
        QValidator.__init__(self)
        self.formatter = formatter
        self.codec = codec

    def validate(self, text):
        import struct

        r1 = self.formatter.validate(text)
        if r1 == QValidator.Acceptable:
            try:
                self.codec.encode(self.formatter.parse(text))
                return r1
            except struct.error:
                return QValidator.Invalid
        return r1


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
        formatter.padding = max(len(formatter.format(valuecodec.maximal)), len(formatter.format(valuecodec.minimal)))
        return formatter

    def createColumnModel(self, hex_widget):
        return HexColumnModel(hex_widget.editor, self._valueCodec, self._formatter, self.spnColumnsOnRow.value())

    def saveToColumn(self, column):
        column.valuecodec = self._valueCodec
        column.formatter = self._formatter
        column.columnsOnRow = self.spnColumnsOnRow.value()
        column.reset()
