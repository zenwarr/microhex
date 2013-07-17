from PyQt4.QtCore import QCoreApplication, QByteArray, QSize
from PyQt4.QtGui import QDialog, QFontDatabase, QColor, QIcon
import os
import threading
import contextlib
import random


applicationPath = ''
guiThread = None
testRun = False


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


class ReadWriteLock(object):
    def __init__(self):
        self._lock = threading.RLock()
        self._canReadCondition = threading.Condition(self._lock)
        self._canWriteCondition = threading.Condition(self._lock)
        self._activeWriter = None  # if there is active writer, this variable hold writer thread id
        self._writeLockCount = 0
        self._readers = {}  # thread identifiers for readers: number of readers
        self._pendingWriters = []  # holds identifiers for threads that wait for writing on _canWriteCondition

    def acquireRead(self, blocking=True, timeout=-1):
        thread_id = threading.get_ident()
        with self._lock:
            ok = False
            if thread_id in self._readers:
                # let thread get another lock if it already has one
                ok = True
            if self._activeWriter is not None and self._activeWriter == thread_id:
                # if thread already has write access, let it read too
                ok = True
            elif self._pendingWriters or self._activeWriter is not None:
                # there are pending writers or active writer: we will not give read access until writers completed
                if blocking:
                    ok = self._canReadCondition.wait_for(self._canReadNow, timeout if timeout >= 0 else None)
            else:
                ok = True

            if ok:
                if thread_id in self._readers:
                    self._readers[thread_id] += 1
                else:
                    self._readers[thread_id] = 1

            return ok

    def releaseRead(self):
        thread_id = threading.get_ident()
        with self._lock:
            if thread_id not in self._readers:
                raise RuntimeError('unlocking ReadWriteLock that was not locked for read')

            self._readers[thread_id] -= 1
            if self._readers[thread_id] == 0:
                del self._readers[thread_id]

                # check if we can let writer to begin. This is possible only if there are no other readers, or
                # all reader threads are waiting for write lock too.
                if self._activeWriter is None and not self._hasParallelReaders():
                    self._canWriteCondition.notify()

    def _canWriteNow(self):
        # thread can write only if there are no other active writers and no reader threads (except current one and ones
        # that are already waiting for write lock)
        thread_id = threading.get_ident()
        return (self._activeWriter is None or self._activeWriter == thread_id) and not self._hasParallelReaders()

    def _canReadNow(self):
        # thread can read only if there are no active writer thread or writer thread is current one; also there should
        # be no threads waiting for write. Reading is also possible if thread already has read lock.
        thread_id = threading.get_ident()
        return (
                   thread_id in self._readers or
                   ((self._activeWriter is None or self._activeWriter == thread_id) and not self._pendingWriters)
        )

    def _hasParallelReaders(self):
        """Return True if there are reader threads (except current one) that are active (not waiting for write lock)
        """
        thread_id = threading.get_ident()
        return not all(tid == thread_id or tid in self._pendingWriters for tid in self._readers)

    def acquireWrite(self, blocking=True, timeout=-1):
        thread_id = threading.get_ident()
        with self._lock:
            ok = False
            if self._activeWriter == thread_id:
                # thread already writes? - no problems, bro!
                ok = True
            elif thread_id in self._readers and not self._hasParallelReaders():
                # if thread already has read lock and there are no other threads reading, we can
                # give write lock immediately. We can be sure that no other threads are writing at this moment,
                # as in this case we cannot have read lock.
                ok = True
            elif self._activeWriter is not None or self._hasParallelReaders():
                # another writer or active reader thread is active. Let's wait.
                if blocking:
                    self._pendingWriters.append(thread_id)
                    ok = self._canWriteCondition.wait_for(self._canWriteNow, timeout if timeout >= 0 else None)
                    del self._pendingWriters[self._pendingWriters.index(thread_id)]
            else:
                # there no other writers or active readers. Seems like we can write just now.
                ok = True

            if ok:
                self._activeWriter = thread_id
                self._writeLockCount += 1

            return ok

    def releaseWrite(self):
        thread_id = threading.get_ident()
        with self._lock:
            if self._activeWriter != thread_id or self._writeLockCount == 0:
                raise RuntimeError('unlocking ReadWriteLock that was not locked for write')

            self._writeLockCount -= 1
            if self._writeLockCount == 0:
                self._activeWriter = None
                if not self._pendingWriters:
                    self._canReadCondition.notify_all()
                elif not self._readers:
                    self._canWriteCondition.notify()

    @property
    @contextlib.contextmanager
    def read(self):
        self.acquireRead()
        try:
            yield
        finally:
            self.releaseRead()

    @property
    @contextlib.contextmanager
    def write(self):
        self.acquireWrite()
        try:
            yield
        finally:
            self.releaseWrite()


def generateRandomColor():
    random.seed()
    return QColor(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))


def getIcon(icon_name):
    icon = QIcon.fromTheme(icon_name)
    if icon.isNull():
        icon = QIcon()
        icon.addFile(':/main/images/' + icon_name + '16.png', QSize(16, 16))
        icon.addFile(':/main/images/' + icon_name + '32.png', QSize(32, 32))
    return icon
