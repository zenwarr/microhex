#!/usr/bin/env python3

import sys

if __name__ == '__main__':
    if sys.version_info.major < 3 or sys.version_info.minor < 2:
        print('Sorry, but your version of Python interpreter is not supported.')
        sys.exit(-1)

    import os
    import hex.main
    import hex.utils as utils

    if hasattr(sys, 'frozen'):
        utils.applicationPath = os.path.dirname(sys.executable)
    else:
        utils.applicationPath = os.path.dirname(os.path.realpath(__file__))
    hex.main.main()
