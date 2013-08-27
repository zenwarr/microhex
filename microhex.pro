CONFIG -= debug_and_release debug_and_release_target
TEMPLATE = subdirs
CONFIG += ordered

SUBDIRS = $$PWD/src/documents $$PWD/src/hex

include(config.pri)

run_file.files = $$PWD/src/microhex.py
run_file.path = $$INSTALL_PATH
INSTALLS += run_file

TRANSLATIONS += $$PWD/src/translations/russian.ts

transl.files = $$PWD/src/translations/*.qm
transl.path = $$INSTALL_PATH/translations
transl.CONFIG += no_check_exist
INSTALLS += transl

docs.files = $$PWD/docs/microhex.conf
docs.path = $$INSTALL_PATH/docs
INSTALLS += docs

settings.files = $$PWD/src/settings-default/*
settings.path = $$INSTALL_PATH/settings-default
INSTALLS += settings

