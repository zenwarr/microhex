from PyQt4.QtCore import QAbstractItemModel, Qt, QModelIndex
from PyQt4.QtGui import QWidget, QVBoxLayout, QHBoxLayout, QTreeView, QToolButton, QIcon, QDialogButtonBox, QColor
import hex.datatypes as datatypes
import hex.utils as utils
from PyQt4.QtCore import QAbstractItemModel, Qt, QModelIndex
from PyQt4.QtGui import QWidget, QVBoxLayout, QHBoxLayout, QTreeView, QToolButton, QIcon, QDialogButtonBox
import hex.datatypes as datatypes
import hex.utils as utils
import difflib


class InspectorModel(QAbstractItemModel):
    InstantiatedRole, DecodedValueRole, LabelRole = Qt.UserRole + 1, Qt.UserRole + 2, Qt.UserRole + 3

    class TypeData:
        def __init__(self, label, instantiated):
            self.label = label
            self.instantiated = instantiated
            self.cachedValue = None

        @property
        def displayName(self):
            return self.label or datatypes.TypeManager.splitQualifiedName(self.instantiated.template.qualifiedName)[1]


    def __init__(self):
        QAbstractItemModel.__init__(self)
        self._types = list()
        self._cursor = None
        self._lastId = 0
        self._memberStrings = dict()

    @property
    def instantiatedTypes(self):
        return [td.instantiated for td in self._types]

    @instantiatedTypes.setter
    def instantiatedTypes(self, new_types):
        self.beginRemoveRows(QModelIndex(), 0, len(self._types))
        self._types.clear()
        self.endRemoveRows()

        for type_to_add in new_types:
            if not isinstance(type_to_add, (tuple, list)):
                self.appendType(type_to_add)
            else:
                self.appendType(*type_to_add)

    @property
    def cursor(self):
        return self._cursor

    @cursor.setter
    def cursor(self, new_cursor):
        def compare_values(old_value, new_value, index):
            if old_value is not None and new_value is not None:
                try:
                    matcher = difflib.SequenceMatcher(None, list(old_value.members.keys()),
                                                      list(new_value.members.keys()), autojunk=False)
                except TypeError:
                    # in Python <3.2 there is no autojunk parameter
                    matcher = difflib.SequenceMatcher(None, list(old_value.members.keys()),
                                                      list(new_value.members.keys()))

                for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                    if tag == 'replace' or tag == 'equal':
                        for i, j in zip(range(i1, i2), range(j1, j2)):
                            i_name, j_name = tuple(old_value.members.keys())[i], tuple(new_value.members.keys())[j]
                            compare_values(old_value.members[i_name], new_value.members[j_name],
                                           self.index(j, 0, index))
                    elif tag == 'delete':
                        self.beginRemoveRows(index, i1, i2)
                        self.endRemoveRows()
                    elif tag == 'insert':
                        self.beginInsertRows(index, j1, j2)
                        self.endInsertRows()

            index_parent = index.parent()
            self.dataChanged.emit(index.sibling(index.row(), 0), index.sibling(index.row(),
                                                                               self.columnCount(index_parent) - 1))

        self._cursor = new_cursor
        for row_index, td in enumerate(self._types):
            old_value = td.cachedValue
            td.cachedValue = None
            compare_values(old_value, self._getDecodedValue(td), self.index(row_index, 0))

    def insertType(self, index, template, context=None, label=None, notify_model=True):
        if isinstance(template, str):
            template = datatypes.globalTypeManager().getTemplateChecked(template)
        elif template is None:
            raise TypeError('template not found')

        if context is None:
            context = datatypes.InstantiateContext()

        if index is None:
            index = len(self._types)

        if notify_model:
            self.beginInsertRows(QModelIndex(), index, index)
        self._types.insert(index, self.TypeData(label, datatypes.InstantiatedType(template, context)))
        if notify_model:
            self.endInsertRows()
        return self.index(index, 0)

    def appendType(self, template, context=None, display_name=None):
        return self.insertType(None, template, context, display_name)

    def removeType(self, index, notify_model=True):
        if 0 <= index < self.rowCount():
            if notify_model:
                self.beginRemoveRows(QModelIndex(), index, index)
            del self._types[index]
            if notify_model:
                self.endRemoveRows()

    def replaceTypeAtIndex(self, index, template, context=None, display_name=None):
        if 0 <= index < len(self._types):
            self.removeType(index, notify_model=False)
            self.insertType(index, template, context, display_name, notify_model=False)
            self.dataChanged.emit(self.index(index, 0), self.index(index, self.columnCount()))

    def flags(self, index):
        if index.isValid():
            flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
            # if index.column() == 1:
            #     flags |= Qt.ItemIsEditable
            return flags
        return 0

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            value = self._valueFromIndex(index)
            if value is not None:
                parentValue = value.parentValue

                if role == self.InstantiatedRole:
                    return value.instantiatedType
                elif role == self.DecodedValueRole:
                    return value
                elif role == Qt.DisplayRole or role == Qt.EditRole:
                    if index.column() == 0:
                        if parentValue is None:
                            return self._types[index.row()].displayName
                        elif 0 <= index.row() < len(parentValue.members):
                            return tuple(parentValue.members.keys())[index.row()]
                    else:
                        if value.decodedValue is not None:
                            return self._sanitizeString(str(value.decodedValue))
                        elif value.decodeStatus == datatypes.Value.StatusInvalid and value.decodeStatusText:
                            return '[{0}]'.format(value.decodeStatusText)
                        else:
                            return None
                elif role == Qt.ForegroundRole:
                    if value.decodeStatus == datatypes.Value.StatusInvalid:
                        return QColor(Qt.red)
                elif role == Qt.ToolTipRole:
                    type_name = value.instantiatedType.template.qualifiedName
                    t = utils.tr('Label: {0}\nType: {1}').format(index.data(self.LabelRole) or '<none>', type_name)
                    if value.comment:
                        t += '\n' + value.comment
                    if value.decodeStatusText:
                        if value.decodeStatus == datatypes.Value.StatusInvalid:
                            status_desc = utils.tr('Error')
                        elif value.decodeStatus == datatypes.Value.StatusWarning:
                            status_desc = utils.tr('Warning')
                        else:
                            status_desc = utils.tr('Decode message')
                        t += '\n{0}: {1}'.format(status_desc, value.decodeStatusText)
                    return t
                elif role == self.LabelRole:
                    if parentValue is None:
                        return self._types[index.row()].label or ''
                    elif 0 <= index.row() < len(parentValue.members):
                        return tuple(parentValue.members.keys())[index.row()]

    def _getDecodedValue(self, td):
        if td.cachedValue is None and self._cursor is not None:
            try:
                template = td.instantiated.template
                context = template.typeManager.prepareContext(td.instantiated.context, template, self._cursor)
                td.cachedValue = td.instantiated.template.decode(context)
            except datatypes.DecodeError as err:
                td.cachedValue = err.value
        return td.cachedValue

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            return self.indexFromValue(self._getDecodedValue(self._types[row]), row, column)
        else:
            parentValue = self._valueFromIndex(parent)
            if parentValue is not None:
                return self.indexFromValue(parentValue.members[tuple(parentValue.members.keys())[row]], row, column)
        return QModelIndex()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            parentValue = self._valueFromIndex(parent)
            return len(parentValue.members) if parentValue is not None else 0
        else:
            return len(self._types)

    def columnCount(self, parent=QModelIndex()):
        return 2

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section == 0:
                return utils.tr('Type')
            elif section == 1:
                return utils.tr('Value')

    def parent(self, index):
        if index.isValid():
            value = self._valueFromIndex(index)
            if value is not None:
                return self.indexFromValue(value.parentValue)
        return QModelIndex()

    _trans_dict = {'\x00': '\\0', '\x07': '\\a', '\x08': '\\b', '\x09': '\\t', '\x0a': '\\n', '\x0b': '\\v',
                   '\x0c': '\\f', '\x0d': '\\r', '\x1b': '\\e', '\x7f': '\\x7f', '\u2028': '\\u2028',
                   '\u2029': '\\u2029'}
    for x in range(1, 32):
        if x not in _trans_dict:
            _trans_dict[chr(x)] = '\\x' + str(x)

    _sanitize_trans_table = str.maketrans(_trans_dict)

    @staticmethod
    def _sanitizeString(text):
        return text.translate(InspectorModel._sanitize_trans_table)

    def topParentIndex(self, value):
        while value is not None and value.parentValue is not None:
            value = value.parentValue
        return self.indexFromValue(value)

    def indexFromValue(self, value, row=None, column=0):
        if value is None:
            if row is not None:
                return self.createIndex(row, column)
            return QModelIndex()

        if row is None:
            if value.parentValue is None:
                row = utils.indexOf(self._types, lambda td: td.cachedValue is value)
            else:
                parentValue = value.parentValue
                row = utils.indexOf(parentValue.members, lambda key: parentValue.members[key] is value)

            if row is None:
                return QModelIndex()

        if value.parentValue is None:
            top_row = row
        else:
            d = value
            while d.parentValue is not None:
                d = value.parentValue
            top_row = utils.indexOf(self._types, lambda td: td.cachedValue is d)

        member_name = str(top_row) + '-' + value.getFullMemberName()
        str_id = utils.keyFromValue(self._memberStrings, lambda x: x == member_name)
        if str_id is None:
            self._lastId += 1
            self._memberStrings[self._lastId] = member_name
            str_id = self._lastId

        return self.createIndex(row, column, str_id)

    def _valueFromIndex(self, index):
        if index.isValid() and index.internalId() in self._memberStrings:
            m_str = self._memberStrings[index.internalId()]
            top_row = int(m_str[:m_str.index('-')])
            member = m_str[m_str.index('-') + 1:]
            if not member:
                return self._getDecodedValue(self._types[top_row])
            else:
                return self._getDecodedValue(self._types[top_row]).getMemberValue(member)


class InspectorWidget(QWidget):
    def __init__(self, parent):
        QWidget.__init__(self, parent)

        self.inspectorModel = InspectorModel()

        self.inspectorView = QTreeView(self)
        self.inspectorView.setModel(self.inspectorModel)
        self.inspectorView.setAlternatingRowColors(True)

        self.btnAddType = QToolButton(self)
        self.btnAddType.setIcon(QIcon(':/main/images/plus.png'))
        self.btnAddType.clicked.connect(self._addType)
        self.btnEditType = QToolButton(self)
        self.btnEditType.setIcon(QIcon(':/main/images/pencil.png'))
        self.btnEditType.clicked.connect(self._editType)
        self.btnRemoveType = QToolButton(self)
        self.btnRemoveType.setIcon(QIcon(':/main/images/minus.png'))
        self.btnRemoveType.clicked.connect(self._removeType)

        tool_layout = QHBoxLayout()
        for btn in (self.btnAddType, self.btnEditType, self.btnRemoveType):
            btn.setAutoRaise(True)
            tool_layout.addWidget(btn)
        tool_layout.addStretch()

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addLayout(tool_layout)
        self.layout().addWidget(self.inspectorView)
        
    @property
    def cursor(self):
        return self.inspectorModel.cursor

    @cursor.setter
    def cursor(self, new_cursor):
        self.inspectorModel.cursor = new_cursor

    def _addType(self):
        dlg = TypeChooseDialog(self)
        if dlg.exec_() == TypeChooseDialog.Accepted:
            new_index = self.inspectorModel.appendType(dlg.template, dlg.context, dlg.description)
            if new_index.isValid():
                self.inspectorView.setCurrentIndex(new_index)

    def _editType(self):
        c_index = self.inspectorView.currentIndex()
        if c_index.isValid():
            dlg = TypeReplaceDialog(self, c_index.data(InspectorModel.InstantiatedRole),
                                    c_index.data(InspectorModel.LabelRole))
            if dlg.exec_() == TypeReplaceDialog.Accepted:
                self.inspectorModel.replaceTypeAtIndex(c_index.row(), dlg.template, dlg.context, dlg.description)

    def _removeType(self):
        c_index = self.inspectorView.currentIndex()
        if c_index.isValid():
            self.inspectorModel.removeType(c_index.row())


class TypeChooseDialog(utils.Dialog):
    def __init__(self, parent):
        utils.Dialog.__init__(self, parent, name='type_choose_dialog')
        self.setWindowTitle(utils.tr('Choose type'))

        self.typeChooser = datatypes.TypeChooserWidget(self)
        self.typeChooser.selectedTemplateChanged.connect(lambda t: self.buttonBox.button(QDialogButtonBox.Ok)
                                                                   .setEnabled(t is not None))

        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(self.typeChooser.selectedTemplate is not None)

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.typeChooser)
        self.layout().addWidget(self.buttonBox)

        self.resize(400, 400)
        self.loadGeometry()

    @property
    def instantiated(self):
        return self.typeChooser.instantiated

    @property
    def template(self):
        return self.typeChooser.selectedTemplate

    @property
    def context(self):
        return self.typeChooser.context

    @property
    def description(self):
        return self.typeChooser.description


class TypeReplaceDialog(TypeChooseDialog):
    def __init__(self, parent, instantiated, label=''):
        TypeChooseDialog.__init__(self, parent)

        self.setWindowTitle(utils.tr('Replace type'))
        self.typeChooser.instantiated = instantiated
        self.typeChooser.description = label
