CONFIG -= debug_and_release debug_and_release_target
TEMPLATE = subdirs
CONFIG += ordered

SUBDIRS = $$PWD/src/documents $$PWD/src/hex
