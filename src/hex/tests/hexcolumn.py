import unittest
import struct
import math
from hex.hexcolumn import HexColumnModel
import hex.documents as documents
import hex.valuecodecs as valuecodecs
import hex.formatters as formatters
import hex.utils as utils
import hex.hexwidget as hexwidget


data = b''.join(struct.pack('B', x) for x in range(256))


class HexColumnTest(unittest.TestCase):
    def test(self):
        doc = documents.Document(documents.deviceFromData(data))
        model = HexColumnModel(doc, valuecodecs.IntegerCodec(signed=False),
                               formatters.IntegerFormatter(base=16, padding=2))
        formatter = formatters.IntegerFormatter(base=16, padding=2)
        self.assertEqual(model.rowCount(), math.ceil((utils.MaximalPosition + 1) / 16))
        index = model.firstIndex
        index_count = 0
        while index and not index.virtual:
            if index.data() == '.':
                pass
            self.assertEqual(index.data(), formatter.format(index_count))
            index_count += 1
            index = index.next

        self.assertEqual(index_count, 256)

        self.assertEqual(model.realRowCount(), 256 // 16)
        for row_index in (0, 10, 15, 16, 0x10000000000000000 // 16 - 1):
            self.assertEqual(model.columnCount(row_index), 16)
            if row_index >= 16:
                self.assertEqual(model.realColumnCount(row_index), 0)
            else:
                self.assertEqual(model.realColumnCount(row_index), 16)

            for column_index in (0, 1, 5, 14, 15):
                index = model.index(row_index, column_index)

                self.assertEqual(index.documentPosition, row_index * 16 + column_index)
                self.assertEqual(index.dataSize, 1)
                if row_index >= 16:
                    self.assertEqual(index.documentData, b'')
                else:
                    self.assertEqual(index.documentData, struct.pack('B', row_index * 16 + column_index))

        self.assertEqual(model.realColumnCount(-1), -1)
        self.assertEqual(model.columnCount(-1), -1)
        self.assertEqual(model.columnCount(0xfffffffffffffffffffffffff), -1)

        self.assertEqual(model.indexFromPosition(0), model.firstIndex)
        self.assertEqual(model.indexFromPosition(-1), hexwidget.ModelIndex())
        self.assertEqual(model.indexFromPosition(4), model.index(0, 4))

        ed_index = model.index(0, 10)
        delegate = model.delegateForIndex(ed_index)
        self.assertTrue(delegate)

        self.assertEqual(delegate.index, ed_index)
        self.assertEqual(delegate.data(), ed_index.data())

        delegate._setData('00')
        self.assertEqual(delegate.data(), '00')
        self.assertEqual(ed_index.data(), '0a')
        self.assertTrue(delegate.flags & model.FlagModified)

        delegate.end(save=True)
        self.assertEqual(ed_index.data(), '00')

        delegate = model.delegateForIndex(ed_index)
        delegate._setData('ff')
        delegate.end(save=False)
        self.assertEqual(ed_index.data(), '00')
        self.assertEqual(delegate.data(), 'ff')

        delegate = model.delegateForNewIndex('f', model.index(0, 10))
        self.assertEqual(len(model.document), 257)
        self.assertEqual(delegate.data(), 'f0')
        delegate.end(save=False)
        self.assertEqual(len(model.document), 256)

        delegate = model.delegateForNewIndex('z', model.index(0, 10))
        self.assertIsNone(delegate)
        self.assertEqual(len(model.document), 256)

