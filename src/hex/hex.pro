TEMPLATE = aux

include(../../config.pri)

PYQT_FORMS = ./forms/addbookmarkdialog.ui \
             ./forms/gotodialog.ui \
             ./forms/loadfiledialog.ui \
             ./forms/settingsdialog.ui

pyqt_uic.name = PyQt4 UI Compiler
pyqt_uic.input = PYQT_FORMS
pyqt_uic.output = ${QMAKE_FILE_IN_PATH}/ui_${QMAKE_FILE_BASE}.py
pyqt_uic.commands = $$PYUIC -i 0 -o ${QMAKE_FILE_OUT} ${QMAKE_FILE_IN}
pyqt_uic.CONFIG += no_link target_predeps
QMAKE_EXTRA_COMPILERS += pyqt_uic

PYQT_RESOURCES = ./resources/main.qrc

pyqt_rcc.name = PyQt4 Resource Compiler
pyqt_rcc.input = PYQT_RESOURCES
pyqt_rcc.output = ${QMAKE_FILE_IN_PATH}/qrc_${QMAKE_FILE_BASE}.py
pyqt_rcc.commands = $$PYRCC -py3 -o ${QMAKE_FILE_OUT} ${QMAKE_FILE_IN}
pyqt_rcc.CONFIG += no_link target_predeps
QMAKE_EXTRA_COMPILERS += pyqt_rcc

