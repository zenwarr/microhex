import locale
import os
import sys
import argparse
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
        # hidden option --test, should not be visible in argument list...
        if '--test' in self.arguments():
            try:
                utils.testRun = True
                from hex.test import runTests
                runTests()
            except ImportError:
                pass
            return False

        self.argparser = argparse.ArgumentParser(prog='microhex',
                                                 description=utils.tr('Crossplatform hex-editing software'))
        self.argparser.add_argument('--version', '-v', action='version', version='{0} {1}'.format(self.applicationName(),
                                                                                                  self.applicationVersion()),
                                    help=utils.tr('show application version and exit'))
        self.argparser.add_argument('--reset-settings', dest='resetSettings', action='store_true',
                                    help=utils.tr('reset application settings to defaults'))
        self.argparser.add_argument('--read-only', '-r', dest='readOnly', action='store_true',
                                    help=utils.tr('load files in read-only mode'))
        self.argparser.add_argument('--freeze-size', '-f', dest='freezeSize', action='store_true',
                                    help=utils.tr('freeze size of loaded documents'))
        self.argparser.add_argument('--no-loaddialog', '-nl', dest='noLoadDialog', action='store_true',
                                    help=utils.tr('do not invoke load options dialog'))
        self.argparser.add_argument('files', nargs='*')

        self.args = self.argparser.parse_args()
        # filenames can contain ~ in some cases (unfortunately Qt does not understand it)
        self.args.files = [os.path.expanduser(file) for file in self.args.files]

        if self.args.resetSettings:
            # reset settings and reload
            settings.globalSettings().reset()
            settings.globalQuickSettings().reset()

            # maybe we should retranslate application
            translate.initApplicationTranslation()

        from hex.mainwin import MainWindow
        self.mainWindow = MainWindow(self.args.files)
        self.mainWindow.show()

        return True

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
    started = app.startUp()
    try:
        if started:
            return_code = app.exec_()
        else:
            return_code = 0
    finally:
        app.shutdown()
    return return_code
