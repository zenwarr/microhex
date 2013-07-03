from PyQt4.QtCore import QFileInfo, QDir, QTranslator, QCoreApplication
import hex.utils as utils
import hex.settings as settings
import hex.appsettings as appsettings
import os


BuiltinLanguage = 'English'


class TranslationModule(object):
    def __init__(self, filename=''):
        self.filename = filename
        self.translator = None

    @property
    def language(self):
        return BuiltinLanguage if not self.filename else QFileInfo(self.filename).baseName()

    def __eq__(self, other):
        if not isinstance(other, TranslationModule):
            return NotImplemented
        return self.language.casefold() == other.language.casefold()

    def __ne__(self, other):
        if not isinstance(other, TranslationModule):
            return NotImplemented
        return not self.__eq__(other)


_activeModule = None
_availModules = []


def activeModule():
    return _activeModule


def availableModules():
    global _availModules

    if not _availModules:
        _availModules = [TranslationModule()]
        for fileEntry in QDir(os.path.join(utils.applicationPath, 'translations')).entryInfoList(QDir.Files|QDir.NoDotAndDotDot):
            if fileEntry.suffix() == 'qm':
                _availModules.append(TranslationModule(fileEntry.absoluteFilePath()))

    return _availModules


def initApplicationTranslation():
    global _activeModule

    language = settings.globalSettings()[appsettings.App_Translation]
    if language:
        filename = os.path.join(utils.applicationPath, 'translations/' + language)
        translator = QTranslator()
        if translator.load(filename):
            QCoreApplication.installTranslator(translator)
            _activeModule = TranslationModule(filename)
            _activeModule.translator = translator
        else:
            print('failed to load translation from {0} file'.format(filename))
    else:
        _activeModule = TranslationModule()


def moduleFromLanguage(language):
    language = language.casefold()
    if not language or language == BuiltinLanguage.casefold():
        return availableModules()[0]
    else:
        return utils.first(availableModules(), lambda module: module.language.casefold() == language)
