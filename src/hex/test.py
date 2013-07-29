import unittest
import hex.tests.editor
import hex.tests.integeredit
import hex.tests.hexwidget
import hex.tests.operations

#
# def runTests():
#     module_list = (
#         hex.tests.editor,
#         hex.tests.integeredit,
#         hex.tests.hexwidget,
#         hex.tests.operations,
#     )
#
#     for module in module_list:
#         suite = unittest.TestLoader().loadTestsFromModule(module)
#         unittest.TextTestRunner().run(suite)
#
#
import time
import hex.devices as devices
from hex.editor import Editor
from PyQt4.QtCore import QFile

comp = 10
matches = 0

# # first variant - Python functions
# s = time.time()
# f = open('/home/victor/Diorama - Belle.mp3', 'rb')
# for byte in f.read():
#     if byte == comp:
#         matches += 1
#
# print(time.time() - s)
#
# matches = 0
# # second variant - Qt methods
# s = time.time()
# f = QFile('/home/victor/Diorama - Belle.mp3')
# f.open(QFile.ReadOnly)
# for byte in bytes(f.readAll()):
#     if byte == comp:
#         matches += 1
#
# print(time.time() - s)
#
#
# matches = 0
# # third variant - microhex classes
# s = time.time()
device = devices.deviceFromUrl('file://home/victor/Diorama - Belle.mp3')
# for byte_index in range(len(device)):
#     byte = device.read(byte_index, 1)
#     if byte == comp:
#         matches += 1
#
# print(time.time() - s)


matches = 0
s = time.time()
editor = Editor(device)
for byte in editor.byteRange(0, len(editor)):
    if byte == comp:
        matches += 1
print(time.time() - s)
