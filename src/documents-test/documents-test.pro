QT       += core testlib

TARGET = documents-test
CONFIG   += console qtestlib
TEMPLATE = app

SOURCES += main.cpp \
    ../documents/spans.cpp \
    ../documents/readwritelock.cpp \
    ../documents/matcher.cpp \
    ../documents/document.cpp \
    ../documents/devices.cpp \
    ../documents/clipboard.cpp \
    ../documents/chain.cpp \
    ../documents/sharedwrap.cpp \
    ../documents/base.cpp

HEADERS += \
    ../documents/spans.h \
    ../documents/document.h \
    ../documents/devices.h \
    ../documents/chain.h \
    ../documents/readwritelock.h \
    ../documents/matcher.h \
    tests.h \
    ../documents/clipboard.h \
    ../documents/base.h \
    ../documents/sharedwrap.h

OTHER_FILES += \
    ../documents/TODO.txt

INCLUDEPATH += ../documents/

*g++* {
    QMAKE_CXXFLAGS += -std=c++0x
}

DESTDIR = ../documents
