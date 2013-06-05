import threading
from PyQt4.QtCore import QIODevice


class Device(object):
    def __init__(self, qdevice):
        self.lock = threading.RLock()
        self._qdevice = qdevice
        self._deviceSize = qdevice.size() if qdevice is not None else 0

    @property
    def qdevice(self):
        return self._qdevice

    def __deepcopy__(self):
        return Device(self._qdevice)

    def __len__(self):
        return self._deviceSize

    def seek(self, pos):
        with self.lock:
            self.qdevice.seek(pos)

    def read(self, length):
        with self.lock:
            return bytes(self.qdevice.read(length))
