from PyQt4.QtCore import QFile
from PyQt4.QtGui import QMainWindow
from hex.hexwidget import HexWidget
from hex.editor import Editor
from hex.device import Device


class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.setWindowTitle('Main window')

        file_device = QFile('/home/victor/test.zip')
        file_device.open(QFile.ReadOnly)

        self.hexWidget = HexWidget(self, Editor(Device(file_device)))
        self.setCentralWidget(self.hexWidget)

        self.setFocusProxy(self.hexWidget)
        self.hexWidget.setFocus()

        self.resize(1000, 500)
