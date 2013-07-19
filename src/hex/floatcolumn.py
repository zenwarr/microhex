import hex.hexwidget as hexwidget
import hex.valuecodecs as valuecodecs
import hex.formatters as formatters
import hex.columnproviders as columnproviders
import hex.utils as utils
from PyQt4.QtCore import Qt
from PyQt4.QtGui import QDoubleValidator, QWidget, QFormLayout, QSpinBox, QComboBox, QSizePolicy


class FloatColumnModel(hexwidget.RegularValueColumnModel):
    def __init__(self, editor, valuecodec=None, formatter=None, columns_on_row=4):
        hexwidget.RegularValueColumnModel.__init__(self, editor, valuecodec or valuecodecs.FloatCodec(),
                                                   formatter or formatters.FloatFormatter(), columns_on_row)

    @property
    def regularCellTextLength(self):
        return self.formatter.maximalWidth

    def virtualIndexData(self, index, role=Qt.DisplayRole):
        if role == Qt.EditRole or (role == Qt.DisplayRole and self.editingIndex == index):
            return '0'
        return hexwidget.RegularValueColumnModel.virtualIndexData(self, index, role)

    @property
    def preferSpaced(self):
        return True

    def indexData(self, index, role=Qt.DisplayRole):
        d = hexwidget.RegularValueColumnModel.indexData(self, index, role)
        return d.strip() if (role == Qt.EditRole and d) else d

    def _dataForNewIndex(self, input_text, before_index):
        import struct
        if self.createValidator().validate(input_text, len(input_text))[0] != QDoubleValidator.Invalid:
            try:
                text = input_text or '0'
                return self.valuecodec.encode(self.formatter.parse(text)), text, max(len(input_text), 1)
            except (ValueError, struct.error):
                pass
        return None, -1

    @property
    def defaultCellInsertMode(self):
        return True

    def createValidator(self):
        return QDoubleValidator()


class FloatColumnProvider(columnproviders.AbstractColumnProvider):
    def __init__(self):
        columnproviders.AbstractColumnProvider.__init__(self)
        self.name = utils.tr('Floating point column')
        self.columnModelType = FloatColumnModel

    def createConfigurationWidget(self, parent, hex_widget, column=None):
        return FloatColumnConfigurationWidget(parent, hex_widget, column)


class FloatColumnConfigurationWidget(QWidget, columnproviders.AbstractColumnConfigurationWidget):
    def __init__(self, parent, hex_widget, column):
        QWidget.__init__(self, parent)
        columnproviders.AbstractColumnConfigurationWidget.__init__(self)
        self.hexWidget = hex_widget
        self.column = column

        self.cmbBinaryFormat = QComboBox(self)
        self.cmbBinaryFormat.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        for fmt in (valuecodecs.FloatCodec.FormatFloat, valuecodecs.FloatCodec.FormatDouble):
            self.cmbBinaryFormat.addItem(valuecodecs.FloatCodec.formatName(fmt), fmt)
            if column is not None and column.valuecodec.binaryFormat == fmt:
                self.cmbBinaryFormat.setCurrentIndex(self.cmbBinaryFormat.count() - 1)

        self.spnPrecision = QSpinBox(self)
        self.spnPrecision.setMinimum(0)
        self.spnPrecision.setMaximum(12)
        if column is not None:
            self.spnPrecision.setValue(column.formatter.precision)
        else:
            self.spnPrecision.setValue(6)

        self.spnColumnsOnRow = QSpinBox(self)
        self.spnColumnsOnRow.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.spnColumnsOnRow.setMinimum(1)
        self.spnColumnsOnRow.setMaximum(32)
        if column is not None:
            self.spnColumnsOnRow.setValue(column.columnsOnRow)
        else:
            self.spnColumnsOnRow.setValue(4)

        self.setLayout(QFormLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addRow(utils.tr('Binary format:'), self.cmbBinaryFormat)
        self.layout().addRow(utils.tr('Digits after point:'), self.spnPrecision)
        self.layout().addRow(utils.tr('Columns on row:'), self.spnColumnsOnRow)

    @property
    def _valueCodec(self):
        c = valuecodecs.FloatCodec()
        c.binaryFormat = self.cmbBinaryFormat.itemData(self.cmbBinaryFormat.currentIndex())
        return c

    @property
    def _formatter(self):
        f = formatters.FloatFormatter()
        f.precision = self.spnPrecision.value()
        return f

    def createColumnModel(self, hex_widget):
        return FloatColumnModel(hex_widget.editor, self._valueCodec, self._formatter, self.spnColumnsOnRow.value())

    def saveToColumn(self, column):
        column.valuecodec = self._valueCodec
        column.formatter = self._formatter
        column.columnsOnRow = self.spnColumnsOnRow.value()
        column.reset()

