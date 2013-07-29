#-------------------------------------------------
#
# Project created by QtCreator 2013-07-24T15:46:11
#
#-------------------------------------------------

QT       -= gui

TARGET = documents
TEMPLATE = lib
CONFIG += staticlib

DEFINES += DOCUMENTS_LIBRARY

SOURCES += \
    devices.cpp \
    spans.cpp \
    chain.cpp \
    document.cpp \
    readwritelock.cpp

HEADERS += \
    devices.h \
    spans.h \
    chain.h \
    document.h \
    readwritelock.h

unix:!symbian {
    maemo5 {
        target.path = /opt/usr/lib
    } else {
        target.path = /usr/lib
    }
    INSTALLS += target
}

QMAKE_CXXFLAGS += -std=c++0x

OTHER_FILES += \
    documents.sip \
    configure.py \
    TODO.txt
