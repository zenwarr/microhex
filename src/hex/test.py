import unittest
import hex.tests.editor
import hex.tests.integeredit
import hex.tests.hexwidget
import hex.tests.operations


def runTests():
    module_list = (
        hex.tests.editor,
        hex.tests.integeredit,
        hex.tests.hexwidget,
        hex.tests.operations,
    )

    for module in module_list:
        suite = unittest.TestLoader().loadTestsFromModule(module)
        unittest.TextTestRunner().run(suite)
