from unittest import TestCase
from hex.inspector import InspectorModel
from hex.utils import DataCursor


class InspectorModelTest(TestCase):
    def test_initial_row_count(self):
        m = InspectorModel()
        self.assertEqual(m.rowCount(), 0)

    def test_set_types(self):
        m = InspectorModel()
        m.instantiatedTypes = ('builtins.float', 'builtins.int8')
        self.assertEqual(m.rowCount(), 2)
        self.assertEqual(m.columnCount(), 2)

    def test_get_index(self):
        m = InspectorModel()
        m.instantiatedTypes = ('builtins.uint16', 'builtins.int8')
        self.assertTrue(m.index(0, 0).isValid())
        self.assertTrue(m.index(0, 1).isValid())
        self.assertTrue(m.index(1, 1).isValid())
        self.assertFalse(m.index(2, 0).isValid())

    def test_data(self):
        m = InspectorModel()
        m.instantiatedTypes = ('builtins.uint16', 'builtins.int8')
        m.cursor = DataCursor(b'\x5a\x5a\x7d\xd1')
        self.assertEqual(m.index(0, 1).data(), str(0x5a5a))
        self.assertEqual(m.index(1, 1).data(), str(0x5a))
