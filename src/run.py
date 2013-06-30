import os
import hex.main
import hex.utils as utils

if __name__ == '__main__':
    utils.applicationPath = os.path.dirname(os.path.realpath(__file__))
    hex.main.main()
