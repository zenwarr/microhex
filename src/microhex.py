import os
import sys
import hex.main
import hex.utils as utils

if __name__ == '__main__':
    if hasattr(sys, 'frozen'):
        utils.applicationPath = os.path.dirname(sys.executable)
    else:
        utils.applicationPath = os.path.dirname(os.path.realpath(__file__))
    hex.main.main()
