import locale
import os
import sys
from PyQt4.QtGui import QApplication
import hex.settings as settings
import hex.appsettings as appsettings
import hex.utils as utils
import hex.translate as translate


class Application(QApplication):
    def __init__(self):
        QApplication.__init__(self, sys.argv)
        self.setApplicationName('Microhex')
        self.setOrganizationName('zenwarr')
        self.setOrganizationDomain('http://github.org/zenwarr/hexedit')
        self.setApplicationVersion('0.0.1 indev')

        # initialize settings
        settings.defaultConfigure('microhex')
        appsettings.doRegister()

        for s in (settings.globalSettings(), settings.globalQuickSettings()):
            try:
                s.load()
            except settings.SettingsError as err:
                print(utils.tr('failed to load settings: {0}').format(err))

        translate.initApplicationTranslation()

    def startUp(self):
        if '--test' in self.arguments():
            from hex.test import runTests
            runTests()
        else:
            from hex.mainwin import MainWindow
            self.mainWindow = MainWindow()
            self.mainWindow.show()

    def shutdown(self):
        for s in (settings.globalSettings(), settings.globalQuickSettings()):
            try:
                s.save()
            except settings.SettingsError as err:
                print(utils.tr('failed to save settings: {0}').format(err))


def main():
    locale.setlocale(locale.LC_ALL, '')
    os.chdir(os.path.expanduser('~'))

    app = Application()
    app.startUp()
    try:
        return_code = app.exec_()
    finally:
        app.shutdown()
    return return_code
