import unittest
import hex.tests.integeredit
import hex.tests.hexwidget
import hex.tests.operations
import hex.tests.hexcolumn
import hex.tests.charcolumn


def runTests():
    module_list = (
        hex.tests.integeredit,
        # hex.tests.hexwidget,
        # hex.tests.operations,
        hex.tests.hexcolumn,
        hex.tests.charcolumn,
    )

    for module in module_list:
        suite = unittest.TestLoader().loadTestsFromModule(module)
        unittest.TextTestRunner().run(suite)
