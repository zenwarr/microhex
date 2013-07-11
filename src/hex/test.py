import unittest
import hex.tests.editor
import hex.tests.integeredit
import hex.tests.hexwidget


def runTests():
    module_list = (
        hex.tests.editor,
        hex.tests.integeredit,
        hex.tests.hexwidget,
    )

    for module in module_list:
        suite = unittest.TestLoader().loadTestsFromModule(module)
        unittest.TextTestRunner().run(suite)
