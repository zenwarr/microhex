import hex.editor as editor
import hex.devices as devices


class ByteArrayLoadOptions(object):
    def __init__(self):
        self.readOnly = False
        self.freezeSize = False

def editorFromByteArray(array, options=None):
    if options is None:
        options = ByteArrayLoadOptions()

    device = devices.BufferDevice(array, options.readOnly, options.freezeSize)
    return editor.Editor(device)
