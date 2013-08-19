import hex.models as models
import hex.valuecodecs as valuecodecs
import hex.formatters as formatters
import hex.columnproviders as columnproviders
import hex.utils as utils
from PyQt4.QtCore import Qt
from PyQt4.QtGui import QDoubleValidator, QWidget, QFormLayout, QSpinBox, QComboBox, QSizePolicy, QValidator
import struct


class FloatColumnModel(models.RegularValueColumnModel):
    def __init__(self, document, valuecodec=None, formatter=None, columns_on_row=4):
        models.RegularValueColumnModel.__init__(self, document, valuecodec or valuecodecs.FloatCodec(),
                                                   formatter or formatters.FloatFormatter(), columns_on_row,
                                                   delegate_type=FloatColumnEditDelegate)

    @property
    def regularTextLength(self):
        return self.formatter.maximalWidth

    def virtualIndexData(self, index, role=Qt.DisplayRole):
        if role == Qt.EditRole:
            return '0'
        return models.RegularValueColumnModel.virtualIndexData(self, index, role)

    @property
    def preferSpaced(self):
        return True

    # def textForDocumentData(self, document_data, index, role=Qt.DisplayRole):
    #     d = models.RegularValueColumnModel.textForDocumentData(self, document_data, index, role)
    #     return d

    def _dataForNewIndex(self, input_text, before_index):
        if self.createValidator().validate(input_text, len(input_text)) != QDoubleValidator.Invalid:
            try:
                text = input_text or '0'
                return self.valuecodec.encode(self.formatter.parse(text)), text, max(len(input_text), 1)
            except (ValueError, struct.error):
                pass
        return b'', '', -1

    @property
    def defaultInsertMode(self):
        return True

    def createValidator(self):
        return FloatColumnValidator()


class FloatColumnEditDelegate(models.StandardEditDelegate):
    @property
    def minimalCursorOffset(self):
        return len(self.data()) - len(self.data().lstrip())


class FloatColumnValidator(QValidator):
    def __init__(self):
        QValidator.__init__(self)
        self._qvalidator = QDoubleValidator()

    def validate(self, text, cursor_pos):
        adjusted_cursor_pos = cursor_pos - (len(text) - len(text.lstrip()))
        status, text, new_cursor_pos = self._qvalidator.validate(text.strip(), adjusted_cursor_pos)
        return status


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
        return FloatColumnModel(hex_widget.document, self._valueCodec, self._formatter, self.spnColumnsOnRow.value())

    def saveToColumn(self, column):
        column.valuecodec = self._valueCodec
        column.formatter = self._formatter
        column.columnsOnRow = self.spnColumnsOnRow.value()
        column.reset()

