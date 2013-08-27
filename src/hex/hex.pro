CONFIG -= debug_and_release debug_and_release_target
unix {
    TEMPLATE = aux
}
win32 {
    TEMPLATE = lib  # TEMPLATE = aux has strange behaviour on Windows: generated makefiles contain empty rule to
                    # make target 'first' and it is impossible to make QMAKE_EXTRA_COMPILERS execute. Side effect of
                    # this workaround is that compiler will create empty library (hex.dll/hex.so)
}

include(../../config.pri)

PYQT_FORMS = $$PWD/forms/addbookmarkdialog.ui \
             $$PWD/forms/gotodialog.ui \
             $$PWD/forms/loadfiledialog.ui \
             $$PWD/forms/settingsdialog.ui

pyqt_uic.name = PyQt4 UI Compiler
pyqt_uic.input = PYQT_FORMS
pyqt_uic.output = ${QMAKE_FILE_PATH}/ui_${QMAKE_FILE_BASE}.py
pyqt_uic.commands = $$PYUIC -i 0 -o ${QMAKE_FILE_OUT} ${QMAKE_FILE_IN}
pyqt_uic.CONFIG += no_link target_predeps
pyqt_uic.variable_out = python_forms.files
QMAKE_EXTRA_COMPILERS += pyqt_uic

PYQT_RESOURCES = $$PWD/resources/main.qrc

pyqt_rcc.name = PyQt4 Resource Compiler
pyqt_rcc.input = PYQT_RESOURCES
pyqt_rcc.output = ${QMAKE_FILE_PATH}/qrc_${QMAKE_FILE_BASE}.py
pyqt_rcc.commands = $$PYRCC -py3 -o ${QMAKE_FILE_OUT} ${QMAKE_FILE_IN}
pyqt_rcc.CONFIG += no_link target_predeps
pyqt_rcc.variable_out = python_resources.files
QMAKE_EXTRA_COMPILERS += pyqt_rcc


python_modules.files += $$PWD/*.py
python_modules.path = $$INSTALL_PATH/hex
python_modules.CONFIG += no_check_exist
INSTALLS += python_modules

python_resources.files += $$PWD/resources/__init__.py
python_resources.path = $$INSTALL_PATH/hex/resources
python_resources.CONFIG += no_check_exist
INSTALLS += python_resources

python_forms.files += $$PWD/forms/__init__.py
python_forms.path = $$INSTALL_PATH/hex/forms
python_forms.CONFIG += no_check_exist
INSTALLS += python_forms
