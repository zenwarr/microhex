QT = core gui
TARGET = documents
TEMPLATE = lib
CONFIG += staticlib
CONFIG -= debug_and_release debug_and_release_target
DEFINES += DOCUMENTS_LIBRARY

*g++* {
    QMAKE_CXXFLAGS += -std=c++0x
}

INCLUDEPATH += $$PWD

include(../../config.pri)

SOURCES += \
    devices.cpp \
    spans.cpp \
    chain.cpp \
    document.cpp \
    readwritelock.cpp \
    matcher.cpp \
    clipboard.cpp \
    sharedwrap.cpp \
    base.cpp

HEADERS += \
    devices.h \
    spans.h \
    chain.h \
    document.h \
    readwritelock.h \
    matcher.h \
    clipboard.h \
    base.h \
    sharedwrap.h

OTHER_FILES += \
    documents.sip \
    configure.py \
    TODO.txt

# command to build Python extension which will be used by application. Makefile for this library built by
# configure.py script which uses SIP utility modules. This command will create documents/documents.so (on linux)
# or documents/documents.pyd (on windows) file that we should copy to install location.
QMAKE_POST_LINK = $$PYTHON3 $$PWD/configure.py $$OUT_PWD && $$MAKE -f $$OUT_PWD/Makefile-sip

unix {
    lib_file.files = $$OUT_PWD/documents.so
}
win32 {
    lib_file.files = $$OUT_PWD/documents.pyd
}
lib_file.path = $$INSTALL_PATH/hex
lib_file.CONFIG += no_check_exist
INSTALLS += lib_file
