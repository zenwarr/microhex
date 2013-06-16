import unittest
import hex.tests.editor
import hex.tests.integeredit


def runTests():
    module_list = (
        hex.tests.editor,
        hex.tests.integeredit
    )

    for module in module_list:
        suite = unittest.TestLoader().loadTestsFromModule(module)
        unittest.TextTestRunner().run(suite)
