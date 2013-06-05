import locale
import os
import sys
from PyQt4.QtGui import QApplication


class Application(QApplication):
    def __init__(self):
        QApplication.__init__(self, sys.argv)
        self.setApplicationName('hexedit')
        self.setOrganizationName('zenwarr')
        self.setOrganizationDomain('http://github.org/zenwarr/hexedit')
        self.setApplicationVersion('0.0.1 indev')

    def startUp(self):
        from hex.mainwin import MainWindow
        self.mainWindow = MainWindow()
        self.mainWindow.show()

    def shutdown(self):
        pass


def main():
    locale.setlocale(locale.LC_ALL, '')
    os.chdir(os.path.expanduser('~'))

    app = Application()
    app.startUp()
    return_code = app.exec_()
    app.shutdown()
    return return_code
