import os

if __name__ == '__main__':
    build_module_filename = os.path.join(os.path.dirname(__file__), 'build.py')
    if os.path.exists(build_module_filename):
        import imp
        build_module = imp.load_source('builder', build_module_filename)
        builder = build_module.Builder(os.path.dirname(__file__))
        builder.build()

    import hex.main
    import hex.utils as utils

    utils.applicationPath = os.path.dirname(os.path.realpath(__file__))
    hex.main.main()
