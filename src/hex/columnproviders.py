from PyQt4.QtGui import QWidget, QFormLayout, QVBoxLayout, QDialogButtonBox, QLineEdit, QSizePolicy, QComboBox
from PyQt4.QtCore import Qt
import hex.utils as utils
import hex.valuecodecs as valuecodecs
import hex.formatters as formatters
import hex.encodings as encodings


class AbstractColumnProvider(object):
    def __init__(self):
        pass

    def createConfigurationWidget(self, parent, hex_widget, column=None):
        pass


class AbstractColumnConfigurationWidget(object):
    def __init__(self):
        pass

    def createColumnModel(self, hex_widget):
        pass


_providers = None


def availableProviders():
    global _providers

    if _providers is None:
        from hex.hexcolumn import HexColumnProvider
        from hex.charcolumn import CharColumnProvider

        _providers = [HexColumnProvider(), CharColumnProvider()]

    return _providers


def providerForColumnModel(column_model):
    for prov in availableProviders():
        if isinstance(column_model, prov.columnModelType):
            return prov
    return None


class CreateColumnDialog(utils.Dialog):
    def __init__(self, parent, hex_widget):
        utils.Dialog.__init__(self, parent, name='create_column_dialog')
        self.hexWidget = hex_widget
        self.configWidget = None

        self.setWindowTitle(utils.tr('Add column'))
        self.setLayout(QVBoxLayout())

        self.cmbColumnProvider = QComboBox(self)
        self.cmbColumnProvider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.layout().addWidget(self.cmbColumnProvider)
        for provider in availableProviders():
            self.cmbColumnProvider.addItem(provider.name, provider)

        self.txtColumnName = QLineEdit(self)
        forml = QFormLayout()
        forml.addRow(utils.tr('Name:'), self.txtColumnName)
        self.layout().addLayout(forml)

        self.cmbColumnProvider.currentIndexChanged[int].connect(self._onCurrentProviderChanged)

        self.layout().addStretch()

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.layout().addWidget(self.buttonBox)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self._onCurrentProviderChanged(self.cmbColumnProvider.currentIndex())

    def _onCurrentProviderChanged(self, index):
        provider = self.cmbColumnProvider.itemData(index)
        if self.configWidget is not None:
            self.configWidget.deleteLater()
            self.configWidget = None

        if provider is not None:
            self.configWidget = provider.createConfigurationWidget(self, self.hexWidget)
            self.layout().insertWidget(2, self.configWidget)

    def createColumnModel(self):
        model = self.configWidget.createColumnModel(self.hexWidget)
        model.name = self.txtColumnName.text()
        return model


class ConfigureColumnDialog(utils.Dialog):
    def __init__(self, parent, hex_widget, column_model):
        utils.Dialog.__init__(self, parent, name='configure_column_dialog')
        self.hexWidget = hex_widget
        self.columnModel = column_model

        self.setWindowTitle(utils.tr('Setup column {0}').format(column_model.name))
        self.setLayout(QVBoxLayout())

        self.txtColumnName = QLineEdit(self)
        forml = QFormLayout()
        forml.addRow(utils.tr('Name:'), self.txtColumnName)
        self.layout().addLayout(forml)
        self.txtColumnName.setText(column_model.name)

        self.provider = providerForColumnModel(column_model)
        if self.provider is not None:
            self.configWidget = self.provider.createConfigurationWidget(self, hex_widget, column_model)
            self.layout().addWidget(self.configWidget)
        else:
            self.configWidget = None

        self.txtColumnName.setEnabled(self.configWidget is not None)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.layout().addWidget(self.buttonBox)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def accept(self):
        if self.configWidget is not None:
            self.configWidget.saveToColumn(self.columnModel)
            self.columnModel.name = self.txtColumnName.text()
        utils.Dialog.accept(self)
