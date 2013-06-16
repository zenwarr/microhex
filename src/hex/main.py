import locale
import os
import sys
from PyQt4.QtGui import QApplication
import hex.settings as settings
import hex.appsettings as appsettings
import hex.utils as utils


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
    build_module_filename = os.path.join(os.path.dirname(__file__), 'build.py')
    if os.path.exists(build_module_filename):
        import imp
        build_module = imp.load_source('builder', build_module_filename)
        builder = build_module.Builder(os.path.dirname(__file__))
        builder.build()

    locale.setlocale(locale.LC_ALL, '')
    os.chdir(os.path.expanduser('~'))

    app = Application()
    app.startUp()
    try:
        return_code = app.exec_()
    finally:
        app.shutdown()
    return return_code
