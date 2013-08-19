import unittest
import hex.documents as documents
import hex.encodings as encodings
import hex.hexwidget as hexwidget
from hex.charcolumn import CharColumnModel
from PyQt4.QtGui import QFont

data = b'\xd1\x82\xd0\xb5\xd0\xba\xd1\x81\xd1\x82\x31\x32\x33'

class CharColumnTest(unittest.TestCase):
    def test(self):
        doc = documents.Document(documents.deviceFromData(data))
        model = CharColumnModel(doc, encodings.getCodec('utf-8'), QFont())

        self.assertEqual(model.realRowCount(), 1)
        self.assertEqual(model.realColumnCount(0), 13)

        r = 'т е к с т 123'
        for char_index in range(len(data)):
            index = model.index(0, char_index)
            self.assertEqual(index.data(), r[char_index])

        delegate = model.delegateForIndex(model.firstRealIndex)
        self.assertEqual(delegate.nextEditIndex, model.index(0, 2))
        self.assertEqual(delegate.previousEditIndex, hexwidget.ModelIndex())

        self.assertEqual(model.delegateForIndex(model.index(0, 1)).nextEditIndex, model.index(0, 2))
