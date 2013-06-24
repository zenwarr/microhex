from PyQt4.QtCore import QCoreApplication
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
