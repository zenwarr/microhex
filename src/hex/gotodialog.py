from hex.forms.ui_gotodialog import Ui_GotoDialog
import hex.utils as utils


class GotoDialog(utils.Dialog):
    def __init__(self, parent, hex_widget):
        utils.Dialog.__init__(self, parent)
        self.ui = Ui_GotoDialog()
        self.ui.setupUi(self)
        self.loadGeometry()

        self.hexWidget = hex_widget

        self.ui.intAddress.number = hex_widget.caretPosition
        self.ui.intAddress.selectAll()

    @property
    def address(self):
        return self.ui.intAddress.number
