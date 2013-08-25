QT       = core gui testlib
CONFIG -= debug_and_release debug_and_release_target

TARGET = documents-test
CONFIG   += console qtestlib
TEMPLATE = app

*g++* {
    QMAKE_CXXFLAGS += -std=c++0x
}

DESTDIR = ../documents

INCLUDEPATH += ../documents/

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

