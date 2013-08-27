# here you should specify commands to execute required tools, as well as other parameters.

# INSTALL_PATH is path to directory (without closing slash) where application will be installed with
# 'make install' command.

unix {
    PYTHON3 = python3
    MAKE = make
    PYUIC = pyuic4
    PYRCC = pyrcc4
    INSTALL_PATH =   # NOTE: you should manually define this
}
win32 {
    PYTHON3 = python
    MAKE = mingw32-make
    PYUIC = pyuic4
    PYRCC = pyrcc4
    INSTALL_PATH =   # NOTE: you should manually define this
}
