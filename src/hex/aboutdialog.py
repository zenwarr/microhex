from PyQt4.QtGui import QDialog, QVBoxLayout, QTabWidget, QPushButton, QLabel, QTextBrowser
from PyQt4.QtCore import QCoreApplication, QFile, Qt
import hex.utils as utils


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)

        self.setFixedSize(500, 500)
        self.setWindowTitle(utils.tr('About MicroHex'))

        layout = QVBoxLayout(self)

        self.label = QLabel(self)
        self.label.setTextFormat(Qt.RichText)
        self.label.setText(utils.tr('MicroHex version {0}, (c) 2013 zenwarr<br><a href="{1}">{1}</a>')
                           .format(QCoreApplication.applicationVersion(), QCoreApplication.organizationDomain()))
        self.label.setOpenExternalLinks(True)

        self.tabWidget = QTabWidget(self)
        self.copyingText = QTextBrowser(self)
        self.copyingText.setOpenExternalLinks(True)
        self.tabWidget.addTab(self.copyingText, utils.tr('License'))
        self.creditsText = QTextBrowser(self)
        self.creditsText.setOpenExternalLinks(True)
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

        self.message = QLabel(self)
        self.message.setTextFormat(Qt.RichText)
        self.message.setWordWrap(True)
        self.message.setText('''Unfortunately, i have no enough time to support this project anymore. If you like this
                             application and have free time, i'd be glad if you help this project by coding. You can
                             contact me in order to get any information related to Microhex and its code.''')

        layout.addWidget(self.label)
        layout.addWidget(self.tabWidget)
        layout.addWidget(self.message)
        layout.addWidget(self.okButton)
