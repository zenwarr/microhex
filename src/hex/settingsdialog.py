from PyQt4.QtGui import QDialogButtonBox, QListWidgetItem, QMessageBox
from hex.forms.ui_settingsdialog import Ui_SettingsDialog
import hex.utils as utils
import hex.settings as settings
import hex.translate as translate


globalSettings = settings.globalSettings()


class SettingsDialog(utils.Dialog):
    class _PageData(object):
        def __init__(self):
            self.title = ''
            self.topicItem = None
            self.page = None
            self.inited = False

    def __init__(self, parent):
        utils.Dialog.__init__(self, parent, name='settings_dialog')

        self.ui = Ui_SettingsDialog()
        self.ui.setupUi(self)
        self.loadGeometry()

        self._pages = []

        self.ui.lstPages.currentItemChanged.connect(self._onCurrentPageItemChanged)
        self.ui.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self._save)
        self.ui.buttonBox.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._reset)

        self._addStandardPages()

    def _addStandardPages(self):
        standard_pages = (
            (utils.tr('Loading'), self.ui.pageLoading),
            (utils.tr('Misc'), self.ui.pageMisc),
            (utils.tr('Translation'), self.ui.pageTranslation)
        )

        for page in standard_pages:
            self._addPage(page[0], page[1])

    def _addPage(self, page_name, page_widget):
        page_data = self._PageData()
        page_data.title = page_name
        page_data.page = page_widget
        page_data.topicItem = QListWidgetItem(page_name)
        self._pages.append(page_data)

        self.ui.lstPages.addItem(page_data.topicItem)
        if not self.ui.lstPages.currentItem():
            self.ui.lstPages.setCurrentItem(page_data.topicItem)

    def _onCurrentPageItemChanged(self, new_item):
        if new_item is None:
            self.ui.pagesStack.setCurrentIndex(-1)
        else:
            page_data = self._pages[self.ui.lstPages.row(new_item)]
            if not page_data.inited:
                # try to initialize page...
                self._initStandardPage(page_data)
                page_data.inited = True
            self.ui.pagesStack.setCurrentWidget(page_data.page)

    def _initStandardPage(self, page_data):
        if page_data.page is self.ui.pageLoading:
            self.ui.maximalRAMLoadSize.number = globalSettings['files.max_memoryload_size']
        elif page_data.page is self.ui.pageMisc:
            self.ui.chkIntegerEditUppercase.setChecked(globalSettings['integeredit.uppercase'])

            self.ui.cmbIntegerEditStyle.clear()
            for style_data in ((utils.tr('No style'), 'none'), (utils.tr('C'), 'c'), (utils.tr('Assembler'), 'asm')):
                self.ui.cmbIntegerEditStyle.addItem(style_data[0], style_data[1])

            self.ui.cmbIntegerEditStyle.setCurrentIndex(self.ui.cmbIntegerEditStyle.findData(
                                globalSettings['integeredit.default_style']))
        elif page_data.page is self.ui.pageTranslation:
            self.ui.cmbTranslations.clear()

            index = 0
            for module in translate.availableModules():
                self.ui.cmbTranslations.addItem(module.language.capitalize(), module.language)
                if module == translate.activeModule():
                    self.ui.cmbTranslations.setCurrentIndex(index)
                index += 1

    def accept(self):
        self._save()
        utils.Dialog.accept(self)

    def _save(self):
        for page_data in self._pages:
            if page_data.inited:
                self._saveStandardPage(page_data)

    def _saveStandardPage(self, page_data):
        if page_data.page is self.ui.pageLoading:
            globalSettings['files.max_memoryload_size'] = self.ui.maximalRAMLoadSize.number
        elif page_data.page is self.ui.pageMisc:
            globalSettings['integeredit.uppercase'] = self.ui.chkIntegerEditUppercase.isChecked()
            style_index = self.ui.cmbIntegerEditStyle.currentIndex()
            globalSettings['integeredit.default_style'] = self.ui.cmbIntegerEditStyle.itemData(style_index)
        elif page_data.page is self.ui.pageTranslation:
            translation_index = self.ui.cmbTranslations.currentIndex()
            globalSettings['app.translation'] = self.ui.cmbTranslations.itemData(translation_index)

    def _reset(self):
        if QMessageBox.question(self, utils.tr('Restore defaults'),
                                utils.tr('Do you really want to reset all application settings right now? '
                                'This action cannot be undone'), QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            globalSettings.reset()
            for page in self._pages:
                page.inited = False
            self._onCurrentPageItemChanged(self.ui.lstPages.currentItem())
