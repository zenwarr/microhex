#-------------------------------------------------
#
# Project created by QtCreator 2013-07-25T20:38:49
#
#-------------------------------------------------

QT       += core testlib
QT       -= gui

TARGET = documents-test
CONFIG   += console
CONFIG   -= app_bundle qtestlib

TEMPLATE = app

SOURCES += main.cpp \
    ../documents/spans.cpp \
    ../documents/document.cpp \
    ../documents/devices.cpp \
    ../documents/chain.cpp \
    ../documents/readwritelock.cpp

HEADERS += \
    ../documents/spans.h \
    ../documents/document.h \
    ../documents/devices.h \
    ../documents/chain.h \
    ../documents/readwritelock.h \
    tests.h

INCLUDEPATH += ../documents/

QMAKE_CXXFLAGS += -std=c++0x
DESTDIR = ../documents
