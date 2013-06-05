import unittest
import hex.tests.editor


if __name__ == '__main__':
    module_list = (
        hex.tests.editor,
    )

    for module in module_list:
        suite = unittest.TestLoader().loadTestsFromModule(module)
        unittest.TextTestRunner().run(suite)
