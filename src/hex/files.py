import hex.editor as editor
import hex.devices as devices
import hex.settings as settings
from PyQt4.QtCore import QFile, QFileInfo


globalSettings = settings.globalSettings()
MaxMemoryLoadSize = globalSettings['files.max_memoryload_size']


class FileLoadOptions(object):
    def __init__(self):
        self.range = None
        self.memoryLoad = False
        self.readOnly = False
        self.freezeSize = False


def editorFromFile(filename, options=None):
    if options is None:
        options = FileLoadOptions()

    device = devices.FileDevice(filename, options.readOnly, options.memoryLoad, options.freezeSize)
    if options.range is not None:
        device = devices.RangeProxyDevice(device, options.range[0], options.range[1], filename)

    return editor.Editor(device)
