import unittest
import hex.tests.integeredit
import hex.tests.hexwidget
import hex.tests.operations
import hex.tests.hexcolumn
import hex.tests.charcolumn
import hex.tests.bigintscrollbar
import hex.tests.datatypes
import hex.tests.documentrange
import hex.tests.cursor
import hex.tests.inspector
import hex.tests.encodings
import hex.tests.cparser


def runTests():
    module_list = (
        hex.tests.integeredit,
        hex.tests.hexwidget,
        hex.tests.operations,
        hex.tests.hexcolumn,
        hex.tests.charcolumn,
        hex.tests.bigintscrollbar,
        hex.tests.datatypes,
        hex.tests.documentrange,
        hex.tests.cursor,
        hex.tests.inspector,
        hex.tests.encodings,
        # hex.tests.cparser
    )

    for module in module_list:
        suite = unittest.TestLoader().loadTestsFromModule(module)
        unittest.TextTestRunner().run(suite)
