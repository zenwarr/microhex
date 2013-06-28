from PyQt4.QtCore import Qt
from PyQt4.QtGui import QWidget, QFormLayout, QComboBox, QVBoxLayout, QDialogButtonBox, QLineEdit, QSizePolicy
import hex.hexwidget as hexwidget
import hex.formatters as formatters
import hex.columnproviders as columnproviders
import hex.integeredit as integeredit
import hex.utils as utils


class AddressColumnModel(hexwidget.ColumnModel):
    def __init__(self, linked_model, formatter=None, base_address=0):
        editor = linked_model.editor if linked_model is not None else linked_model
        hexwidget.ColumnModel.__init__(self, editor)
        self._linkedModel = None
        self.formatter = formatter or formatters.IntegerFormatter()
        self._baseAddress = base_address
        self.linkedModel = linked_model

    @property
    def linkedModel(self):
        return self._linkedModel

    @linkedModel.setter
    def linkedModel(self, model):
        if self._linkedModel is not model:
            if self._linkedModel is not None:
                self._linkedModel.modelReset.disconnect(self.reset)
            self._linkedModel = model
            if self._linkedModel is not None:
                self._linkedModel.modelReset.connect(self.reset)
                self.editor = self._linkedModel.editor
            else:
                self.editor = None
            self.reset()

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
                return self.formatter.format(raw) if self.formatter is not None else raw
            elif role == self.EditorPositionRole:
                return model_index.data(self.EditorPositionRole)
            elif role == self.DataSizeRole:
                return sum(index.data(self.DataSizeRole) for index in hexwidget.index_range(
                    model_index, self._linkedModel.lastRowIndex(index.row), include_last=True
                ))
        return None

    def headerData(self, section, role=Qt.DisplayRole):
        return None

    def indexFromPosition(self, position):
        if self._linkedModel is not None:
            model_index = self._linkedModel.indexFromPosition(position)
            return self.index(model_index.row, 0) if model_index else model_index
        return self._linkedModel

    def indexFlags(self, index):
        if self._linkedModel is not None:
            model_index = self._linkedModel.index(index.row, 0)
            if model_index and model_index.flags & hexwidget.ColumnModel.FlagVirtual:
                return hexwidget.ColumnModel.FlagVirtual
        return 0

    def _maxLengthForSize(self, size):
        """Calculate maximal length of address text for given editor size"""
        sign1 = self._baseAddress > 0
        sign2 = self._baseAddress < len(self._linkedModel.editor)
        max_raw = max(abs(0 - self._baseAddress) + sign1,
                      abs(len(self._linkedModel.editor) - self._baseAddress) + sign2)
        return len(self.formatter.format(max_raw))

    def _updatePadding(self):
        if self.formatter is None:
            self.formatter = formatters.IntegerFormatter()
        self.formatter.padding = self._maxLengthForSize(len(self.editor))

    def reset(self):
        self._updatePadding()
        self.modelReset.emit()


class AddressColumnProvider(columnproviders.AbstractColumnProvider):
    def __init__(self):
        columnproviders.AbstractColumnProvider.__init__(self)
        self.creatable = False
        self.columnModelType = AddressColumnModel

    def createConfigurationWidget(self, parent, hex_widget, column=None):
        return AddressColumnConfigurationWidget(parent, hex_widget, column)


class AddressColumnConfigurationWidget(columnproviders.AbstractColumnConfigurationWidget, QWidget):
    def __init__(self, parent, hex_widget, column):
        columnproviders.AbstractColumnConfigurationWidget.__init__(self)
        QWidget.__init__(self, parent)
        self.hexWidget = hex_widget
        self.column = column

        self.setLayout(QFormLayout())

        self.cmbBase = QComboBox(self)
        self.cmbBase.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.layout().addRow(utils.tr('Base:'), self.cmbBase)
        for base in ((utils.tr('Hex'), 16), (utils.tr('Dec'), 10), (utils.tr('Oct'), 8), (utils.tr('Bin'), 2)):
            self.cmbBase.addItem(base[0], base[1])
        if column is not None:
            self.cmbBase.setCurrentIndex(self.cmbBase.findData(column.formatter.base))

        self.cmbStyle = QComboBox(self)
        self.cmbStyle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.layout().addRow(utils.tr('Style:'), self.cmbStyle)
        for style_data in ((utils.tr('No style'), 'none'), (utils.tr('C'), 'c'), (utils.tr('Assembler'), 'asm')):
            self.cmbStyle.addItem(style_data[0], style_data[1])
        if column is not None:
            self.cmbStyle.setCurrentIndex(self.cmbStyle.findData(column.formatter.styleName))

        self.intBaseAddress = integeredit.IntegerEdit(self)
        self.intBaseAddress.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.layout().addRow(utils.tr('Base address:'), self.intBaseAddress)
        self.intBaseAddress.minimum = -10000000000000
        if column is not None:
            self.intBaseAddress.number = column.baseAddress

    @property
    def _formatter(self):
        formatter = formatters.IntegerFormatter()
        formatter.base = self.cmbBase.itemData(self.cmbBase.currentIndex())
        formatter.style = self.cmbStyle.itemData(self.cmbStyle.currentIndex())
        return formatter

    def createColumnModel(self, hex_widget):
        return AddressColumnModel(None, self._formatter, self.intBaseAddress.number)

    def saveToColumn(self, column):
        column.formatter = self._formatter
        column.baseAddress = self.intBaseAddress.number
        column.reset()


class AddAddressColumnDialog(utils.Dialog):
    def __init__(self, parent, hex_widget, column):
        utils.Dialog.__init__(self, parent, name='add_address_column_dialog')
        self.hexWidget = hex_widget
        self.column = column
        self.setWindowTitle(utils.tr('Add address bar'))

        self.setLayout(QVBoxLayout())

        self.configWidget = AddressColumnConfigurationWidget(self, hex_widget, None)
        self.layout().addWidget(self.configWidget)

        self.txtName = QLineEdit(self)
        self.configWidget.layout().insertRow(0, utils.tr('Name:'), self.txtName)

        self.cmbAlignment = QComboBox(self)
        self.cmbAlignment.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.cmbAlignment.addItem(utils.tr('To the left'), Qt.AlignLeft)
        self.cmbAlignment.addItem(utils.tr('To the right'), Qt.AlignRight)
        self.configWidget.layout().insertRow(1, utils.tr('Position:'), self.cmbAlignment)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout().addWidget(self.buttonBox)

    def addColumn(self):
        model = self.configWidget.createColumnModel(self.hexWidget)
        model.name = self.txtName.text()
        self.hexWidget.addAddressColumn(model, self.cmbAlignment.itemData(self.cmbAlignment.currentIndex()))
