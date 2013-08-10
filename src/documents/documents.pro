TARGET = documents
TEMPLATE = lib
CONFIG += staticlib
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

QMAKE_POST_LINK = $$PYTHON3 $$PWD/configure.py $$OUT_PWD $$DEFINES && $$MAKE -f $$OUT_PWD/Makefile-sip

