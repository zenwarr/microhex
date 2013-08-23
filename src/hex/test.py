import unittest
import hex.tests.integeredit
import hex.tests.hexwidget
import hex.tests.operations
import hex.tests.hexcolumn
import hex.tests.charcolumn
import hex.tests.bigintscrollbar


def runTests():
    module_list = (
        hex.tests.integeredit,
        # hex.tests.hexwidget,
        # hex.tests.operations,
        hex.tests.hexcolumn,
        hex.tests.charcolumn,
        hex.tests.bigintscrollbar,
    )

    for module in module_list:
        suite = unittest.TestLoader().loadTestsFromModule(module)
        unittest.TextTestRunner().run(suite)
