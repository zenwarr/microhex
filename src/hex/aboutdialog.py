from PyQt4.QtGui import QDialog, QVBoxLayout, QTabWidget, QPushButton, QLabel, QTextBrowser
from PyQt4.QtCore import QCoreApplication, QFile, Qt
import hex.utils as utils
import hex.resources.qrc_main


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)

        self.resize(500, 500)
        self.setWindowTitle(utils.tr('About MicroHex'))

        layout = QVBoxLayout(self)

        self.label = QLabel(self)
        self.label.setTextFormat(Qt.RichText)
        self.label.setText(utils.tr('MicroHex version {0}, (c) 2013 zenwarr<br>'
                            '<a href="https://github.com/zenwarr/microhex">https://github.com/zenwarr/microhex</a>')
                            .format(QCoreApplication.applicationVersion()))

        self.tabWidget = QTabWidget(self)
        self.copyingText = QTextBrowser(self)
        self.copyingText.setOpenLinks(False)
        self.tabWidget.addTab(self.copyingText, utils.tr('License'))
        self.creditsText = QTextBrowser(self)
        self.creditsText.setOpenLinks(False)
        self.tabWidget.addTab(self.creditsText, utils.tr('Credits'))

        l_file = QFile(':/main/data/COPYING.html')
        if l_file.open(QFile.ReadOnly | QFile.Text):
            self.copyingText.setText(str(l_file.readAll(), encoding='utf-8'))

        c_file = QFile(':/main/data/CREDITS.html')
        if c_file.open(QFile.ReadOnly | QFile.Text):
            self.creditsText.setText(str(c_file.readAll(), encoding='utf-8'))

        self.okButton = QPushButton(utils.tr('OK'), self)
        self.okButton.clicked.connect(self.close)
        self.okButton.setDefault(True)

        layout.addWidget(self.label)
        layout.addWidget(self.tabWidget)
        layout.addWidget(self.okButton)
