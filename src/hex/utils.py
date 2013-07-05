from PyQt4.QtCore import QCoreApplication, QByteArray
from PyQt4.QtGui import QDialog, QFontDatabase
import os


applicationPath = ''


def first(iterable, default=None):
    try:
        return next(iter(iterable))
    except StopIteration:
        return default


def tr(text, context='utils', disambiguation=None):
    return QCoreApplication.translate(context, text, disambiguation, QCoreApplication.UnicodeUTF8)


def lastFileDialogPath():
    from hex.settings import globalQuickSettings

    qs = globalQuickSettings()
    last_dir = qs['last_filedialog_path']
    return last_dir if isinstance(last_dir, str) else ''


def setLastFileDialogPath(new_path):
    from hex.settings import globalQuickSettings

    qs = globalQuickSettings()
    if os.path.exists(new_path) and os.path.isfile(new_path):
        new_path = os.path.dirname(new_path)
    qs['last_filedialog_path'] = new_path


_q = (
    ('Tb', 1024 * 1024 * 1024 * 1024),
    ('Gb', 1024 * 1024 * 1024),
    ('Mb', 1024 * 1024),
    ('Kb', 1024)
)


def formatSize(size):
    for q in _q:
        if size >= q[1]:
            size = size / q[1]
            postfix = q[0]
            break
    else:
        postfix = 'b'

    num = str(round(size, 2))
    if num.endswith('.0'):
        num = num[:-2]
    return num + ' ' + postfix


class Dialog(QDialog):
    """Dialog that remembers position and size"""

    def __init__(self, parent=None, name=''):
        QDialog.__init__(self, parent)
        self.name = name
        self.loadGeometry()

    def loadGeometry(self):
        import hex.settings as settings

        if self.name:
            saved_geom = settings.globalQuickSettings()[self.name + '.geometry']
            if saved_geom and isinstance(saved_geom, str):
                self.restoreGeometry(QByteArray.fromHex(saved_geom))

    def accept(self):
        self.__save()
        QDialog.accept(self)

    def reject(self):
        self.__save()
        QDialog.reject(self)

    def __save(self):
        import hex.settings as settings
        
        if self.name:
            settings.globalQuickSettings()[self.name + '.geometry'] = str(self.saveGeometry().toHex(), encoding='ascii')


def camelCaseToUnderscore(camel_case):
    return ''.join(('_' + c.lower() if c.isupper() else c) for c in camel_case)


def underscoreToCamelCase(underscore):
    result = list()
    word_start = False
    for ch in underscore:
        if ch == '_':
            word_start = True
        else:
            result.append(ch.upper() if word_start else ch)
            word_start = False
    return ''.join(result)


def isFontInstalled(font_family):
    return font_family in QFontDatabase().families()


def checkRangesIntersect(start1, length1, start2, length2):
    if start2 < start1:
        t = start2
        start2 = start1
        start1 = t

        t = length2
        length2 = length1
        length1 = t

    return not (start2 - start1 <= length1)
