import os
from PyQt4.QtCore import QAbstractTableModel, Qt, QModelIndex
from PyQt4.QtGui import QDialogButtonBox, QListWidgetItem, QMessageBox, QFont, QFontDialog, QWidget, QVBoxLayout, \
                        QHBoxLayout, QComboBox, QPushButton, QListWidget, QTableView, QSizePolicy, QItemDelegate, \
                        QColorDialog, QColor, QInputDialog
from hex.forms.ui_settingsdialog import Ui_SettingsDialog
import hex.utils as utils
import hex.settings as settings
import hex.translate as translate
import hex.appsettings as appsettings
import hex.hexwidget as hexwidget


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

        self.pageTheme = ThemeConfigurationWidget(self)
        self.ui.pagesStack.addWidget(self.pageTheme)

        self.ui.lstPages.currentItemChanged.connect(self._onCurrentPageItemChanged)
        self.ui.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self._save)
        self.ui.buttonBox.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._reset)

        self._addStandardPages()

    def _addStandardPages(self):
        standard_pages = (
            (utils.tr('Misc'), self.ui.pageMisc),
            (utils.tr('Translation'), self.ui.pageTranslation),
            (utils.tr('Hex view'), self.ui.pageHex),
            (utils.tr('Theme'), self.pageTheme)
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
        if page_data.page is self.ui.pageMisc:
            self.ui.chkIntegerEditUppercase.setChecked(globalSettings[appsettings.IntegerEdit_Uppercase])

            self.ui.cmbIntegerEditStyle.clear()
            for style_data in ((utils.tr('No style'), 'none'), (utils.tr('C'), 'c'), (utils.tr('Assembler'), 'asm')):
                self.ui.cmbIntegerEditStyle.addItem(style_data[0], style_data[1])

            self.ui.cmbIntegerEditStyle.setCurrentIndex(self.ui.cmbIntegerEditStyle.findData(
                                globalSettings[appsettings.IntegerEdit_DefaultStyle]))
        elif page_data.page is self.ui.pageTranslation:
            self.ui.cmbTranslations.clear()

            index = 0
            for module in translate.availableModules():
                self.ui.cmbTranslations.addItem(module.language.capitalize(), module.language)
                if module == translate.activeModule():
                    self.ui.cmbTranslations.setCurrentIndex(index)
                index += 1
        elif page_data.page is self.ui.pageHex:
            self.ui.chkAlternatingRows.setChecked(globalSettings[appsettings.HexWidget_AlternatingRows])

            self._hexWidgetFont = appsettings.getFontFromSetting(globalSettings[appsettings.HexWidget_Font])
            self._updateHexWidgetFont()
            self.ui.btnChooseFont.clicked.connect(self._chooseHexWidgetFont)
        elif page_data.page is self.pageTheme:
            self.pageTheme.loadThemes()

    def _chooseHexWidgetFont(self):
        font, ok = QFontDialog.getFont(self._hexWidgetFont, self, utils.tr('Choose font for hex view'))
        if ok:
            self._hexWidgetFont = font
            self._updateHexWidgetFont()

    def _updateHexWidgetFont(self):
        self.ui.lblFont.setText('{0}, {1} pt'.format(self._hexWidgetFont.family(), self._hexWidgetFont.pointSize()))
        self.ui.lblFont.setFont(self._hexWidgetFont)

    def accept(self):
        self._save()
        utils.Dialog.accept(self)

    def _save(self):
        for page_data in self._pages:
            if page_data.inited:
                self._saveStandardPage(page_data)

    def _saveStandardPage(self, page_data):
        if page_data.page is self.ui.pageMisc:
            globalSettings[appsettings.IntegerEdit_Uppercase] = self.ui.chkIntegerEditUppercase.isChecked()
            style_index = self.ui.cmbIntegerEditStyle.currentIndex()
            globalSettings[appsettings.IntegerEdit_DefaultStyle] = self.ui.cmbIntegerEditStyle.itemData(style_index)
        elif page_data.page is self.ui.pageTranslation:
            translation_index = self.ui.cmbTranslations.currentIndex()
            globalSettings[appsettings.App_Translation] = self.ui.cmbTranslations.itemData(translation_index)
        elif page_data.page is self.ui.pageHex:
            globalSettings[appsettings.HexWidget_AlternatingRows] = self.ui.chkAlternatingRows.isChecked()
            globalSettings[appsettings.HexWidget_Font] = self._hexWidgetFont.toString()
        elif page_data.page is self.pageTheme:
            self.pageTheme.saveCurrentTheme()
            globalSettings[appsettings.HexWidget_Theme] = self.pageTheme.themeName

    def _reset(self):
        if QMessageBox.question(self, utils.tr('Restore defaults'),
                                utils.tr('Do you really want to reset all application settings right now? '
                                'This action cannot be undone'), QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            globalSettings.reset()
            for page in self._pages:
                page.inited = False
            self._onCurrentPageItemChanged(self.ui.lstPages.currentItem())


class ThemeConfigurationWidget(QWidget):
    """Themes are stored in directory 'themes' in configuration directory. Each theme file has .mixth extension
    and represents single theme.
    """

    def __init__(self, parent):
        QWidget.__init__(self, parent)

        self.cmbThemes = QComboBox(self)
        self.cmbThemes.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.cmbThemes.currentIndexChanged[int].connect(self._changeCurrentTheme)

        self.btnCopyTheme = QPushButton(self)
        self.btnCopyTheme.setText(utils.tr('Copy theme...'))
        self.btnCopyTheme.clicked.connect(self._copyTheme)

        self.componentsView = QTableView(self)
        self.themeModel = ThemeModel()
        self.componentsView.setModel(self.themeModel)
        self.componentsView.setSelectionBehavior(QTableView.SelectRows)
        self.componentsView.setItemDelegateForColumn(1, ComponentDelegate())
        self.componentsView.setEditTriggers(QTableView.DoubleClicked)

        self.setLayout(QVBoxLayout())
        h_layout = QHBoxLayout()
        h_layout.addWidget(self.cmbThemes)
        h_layout.addWidget(self.btnCopyTheme)
        self.layout().addLayout(h_layout)
        self.layout().addWidget(self.componentsView)

    def resizeEvent(self, event):
        view_size = self.componentsView.size()
        hh = self.componentsView.horizontalHeader()
        hh.resizeSection(0, int((view_size.width() - self.componentsView.verticalHeader().width()) * 0.6))
        hh.setStretchLastSection(True)

    def loadThemes(self, theme_to_select=None):
        if theme_to_select is None:
            theme_to_select = globalSettings[appsettings.HexWidget_Theme]

        self.cmbThemes.clear()
        self.cmbThemes.addItem(utils.tr('Default (unmodifiable)'), '')
        if not theme_to_select:
            self.cmbThemes.setCurrentIndex(0)
        for theme_name in hexwidget.Theme.availableThemes():
            self.cmbThemes.addItem(theme_name.capitalize(), theme_name)
            if theme_name == theme_to_select:
                self.cmbThemes.setCurrentIndex(self.cmbThemes.count() - 1)

    def saveCurrentTheme(self):
        if self.themeModel.theme is not None and self.themeName:
            theme_name = self.themeName
            self.themeModel.theme.save(theme_name)
            self.loadThemes(theme_name)

    @property
    def themeName(self):
        return self.cmbThemes.itemData(self.cmbThemes.currentIndex())

    def _copyTheme(self):
        while True:
            theme_name, ok = QInputDialog.getText(self, utils.tr('Copy theme'), utils.tr('Name for copy of theme:'))
            if not ok:
                break
            if (not theme_name or hexwidget.Theme.themeFromName(theme_name) is not None or not utils.isValidFilename(theme_name)):
                QMessageBox.information(self, utils.tr('Wrong name for theme'), utils.tr('Name for theme is invalid'))
            else:
                break

        if ok:
            self.themeModel.theme.save(theme_name)
            self.loadThemes(theme_name)

    def _changeCurrentTheme(self, index):
        if self.themeName and self.themeModel.modified:
            if QMessageBox.question(self, utils.tr('Save theme'),
                                    utils.tr('Do you want to save "{0}"?').format(self.themeName),
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes:
                self.themeModel.theme.save()

        theme_name = self.cmbThemes.itemData(index)
        if index >= 0 and theme_name is not None:
            theme = hexwidget.Theme.themeFromName(theme_name) or hexwidget.Theme()
        else:
            theme = None
        self.themeModel.theme = theme


class ThemeModel(QAbstractTableModel):
    def __init__(self):
        QAbstractTableModel.__init__(self)
        self._theme = hexwidget.Theme()
        self.modified = False

    @property
    def theme(self):
        return self._theme

    @theme.setter
    def theme(self, new_theme):
        if self._theme is not new_theme:
            self._theme = new_theme
            self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, self.columnCount() - 1))
            self.modified = False

    def rowCount(self, parent_index=QModelIndex()):
        return len(hexwidget.Theme.Components) if not parent_index.isValid() else 0

    def columnCount(self, index=QModelIndex()):
        return 2 if not index.isValid() else 0

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and 0 <= index.row() < len(hexwidget.Theme.Components) and 0 <= index.column() < 2:
            if index.column() == 0:
                if role == Qt.DisplayRole:
                    return self._componentToDisplayName(hexwidget.Theme.Components[index.row()])
            else:
                # if role == Qt.DisplayRole:
                #     return getattr(self._theme, hexwidget.Theme.Components[index.row()] + 'Color').name()
                if role == Qt.DecorationRole and self._theme is not None:
                    return getattr(self._theme, hexwidget.Theme.Components[index.row()] + 'Color')

    def flags(self, index):
        if index.isValid() and index.model() is self and index.column() == 1 and self.theme.name:
            return super().flags(index) | Qt.ItemIsEditable
        return super().flags(index)

    def setData(self, index, value, role=Qt.DecorationRole):
        if index.isValid() and index.model() is self and 0 <= index.row() < self.rowCount() and index.column() == 1:
            if role == Qt.DecorationRole and isinstance(value, QColor) and self._theme is not None:
                setattr(self._theme, hexwidget.Theme.Components[index.row()] + 'Color', value)
                self.dataChanged.emit(self.index(index.row(), 1), self.index(index.row(), 1))
                self.modified = True
                return True

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section == 0:
                return utils.tr('Theme component')
            elif section == 1:
                return utils.tr('Value')

    def _componentToDisplayName(self, comp):
        return utils.tr(''.join((' ' + c.lower() if c.isupper() else c) for c in comp).capitalize())


class ComponentDelegate(QItemDelegate):
    def __init__(self, parent=None):
        QItemDelegate.__init__(self, parent)

    def paint(self, painter, option, index):
        painter.save()
        painter.setPen(Qt.black)
        painter.setBrush(index.data(Qt.DecorationRole))
        painter.drawRoundedRect(option.rect.adjusted(1, 1, -1, -1), 2, 2)
        painter.restore()

    def createEditor(self, parent, option, index):
        return QColorDialog(index.data(Qt.DecorationRole), parent)

    def setEditorData(self, editor, index):
        editor.setCurrentColor(index.data(Qt.DecorationRole))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentColor(), role=Qt.DecorationRole)
