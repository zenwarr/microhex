from PyQt4.QtCore import QAbstractItemModel, Qt, QModelIndex
from PyQt4.QtGui import QWidget, QVBoxLayout, QHBoxLayout, QTreeView, QToolButton, QIcon, QDialogButtonBox, QColor
import hex.datatypes as datatypes
import hex.utils as utils
import difflib
import weakref


class InspectorModel(QAbstractItemModel):
    InstantiatedRole, ValueRole, DecodedValueRole, LabelRole = range(Qt.UserRole + 1, Qt.UserRole + 5)

    class RowData:
        def __init__(self, instantiated_type, label):
            self.instantiatedType = instantiated_type
            self.value = datatypes.Value()  # never none
            self.label = label
            self.children = []
            self.id = 0

        @property
        def displayLabel(self):
            if self.label:
                return self.label
            else:
                return datatypes.TypeManager.splitQualifiedName(self.instantiatedType.template.qualifiedName)[1]

    def __init__(self):
        QAbstractItemModel.__init__(self)
        self._rows = []
        self._rowDataDict = weakref.WeakValueDictionary()  # id -> RowData
        self._lastRowDataId = 0
        self._cursor = None

    @property
    def cursor(self):
        return self._cursor

    @cursor.setter
    def cursor(self, new_cursor):
        self._cursor = new_cursor
        for row_index, row_data in enumerate(self._rows):
            self._updateRow(row_data, self.index(row_index, 0))

    @property
    def types(self):
        return [rd.instantiated_type for rd in self._rows]

    @types.setter
    def types(self, new_types):
        self.clearTypes()
        for t in new_types:
            self.appendType(t)

    def setTypeAtRow(self, row_index, new_type, label=None):
        if 0 <= row_index < len(self._rows):
            self._rows[row_index].instantiatedType = self._getType(new_type)
            if label is not None:
                self._rows[row_index].label = label
            self._updateRow(self._rows[row_index], self.index(row_index, 0))

    def insertTypeAtRow(self, row_index, new_type, label=None):
        if 0 <= row_index <= len(self._rows):
            # prepare RowData object
            rd = self.RowData(self._getType(new_type), '')
            rd.label = label or ''
            rd.id = self._lastRowDataId + 1
            self._lastRowDataId += 1

            # insert row and register it, but do not initialize with value yet
            self.beginInsertRows(QModelIndex(), row_index, row_index)
            self._rows.insert(row_index, rd)
            self._rowDataDict[rd.id] = rd
            self.endInsertRows()

            # and now decode value and append children
            self._updateRow(rd, self.index(row_index, 0))
            return self.index(row_index, 0)

    def appendType(self, new_type, label=None):
        return self.insertTypeAtRow(len(self._rows), new_type, label)

    def removeTypeAtRow(self, row_index):
        if 0 <= row_index < len(self._rows):
            self.beginRemoveRows(QModelIndex(), row_index, row_index)
            del self._rows[row_index]
            self.endRemoveRows()

    def clearTypes(self):
        self.beginResetModel()
        self._rows = []
        self.endResetModel()

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def data(self, index, role=Qt.DisplayRole):
        row_data = self._rowDataFromIndex(index)
        if row_data is None:
            return None
        value = row_data.value

        if role == self.InstantiatedRole:
            return row_data.instantiatedType

        if value is None:
            return None
        elif role == self.ValueRole:
            return value
        elif role == self.DecodedValueRole:
            return value.decodedValue
        elif role == Qt.DisplayRole or role == Qt.EditRole:
            if index.column() == 0:
                return row_data.displayLabel
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
            type_name = row_data.instantiatedType.template.qualifiedName
            t = utils.tr('Label: {0}\nType: {1}').format(row_data.label or '<none>', type_name)
            if value.decodeStatusText:
                if value.decodeStatus == datatypes.Value.StatusInvalid:
                    status_desc = utils.tr('Error')
                elif value.decodeStatus == datatypes.Value.StatusWarning:
                    status_desc = utils.tr('Warning')
                else:
                    status_desc = utils.tr('Decode message')
                t += '\n{0}: {1}'.format(status_desc, value.decodeStatusText)
            if value.comment:
                t += '\n' + utils.tr('Comment: ') + value.comment
            return t
        elif role == self.LabelRole:
            return row_data.label

    def rowCount(self, index=QModelIndex()):
        if not index.isValid():
            return len(self._rows)
        else:
            row_data = self._rowDataFromIndex(index)
            if row_data is not None:
                return len(row_data.children)
        return 0

    def columnCount(self, index=QModelIndex()):
        return 2

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section == 0:
                return utils.tr('Type')
            elif section == 1:
                return utils.tr('Value')

    def index(self, row, column, parent_index=QModelIndex()):
        if self.hasIndex(row, column, parent_index):
            if parent_index.isValid():
                parent_row_data = self._rowDataFromIndex(parent_index)
                if parent_row_data is None:
                    return QModelIndex()
                row_data_id = parent_row_data.children[row].id
            else:
                row_data_id = self._rows[row].id
            return self.createIndex(row, column, row_data_id)
        return QModelIndex()

    def parent(self, index):
        row_data = self._rowDataFromIndex(index)
        if row_data is not None:
            return self.indexFromValue(row_data.value.parentValue)
        return QModelIndex()

    def indexFromValue(self, value):
        def _find_row_of_value(row_data, value):
            for rd_index, rd in enumerate(row_data.children):
                if rd.value is value:
                    return rd_index
            return -1

        if value is None:
            return QModelIndex()

        parents_chain = []
        c_value = value
        while c_value is not None:
            parents_chain.insert(0, c_value)
            c_value = c_value.parentValue

        # find index of topmost parent value at top level
        row_index = utils.first((i for i, rd in enumerate(self._rows) if rd.value is parents_chain[0]), None)
        if row_index is None:
            return QModelIndex()
        row_data = self._rows[row_index]

        # now find index of each parent in its parent row data object, and last index will be row that we can use to
        # create desired QModelIndex
        for parent in parents_chain[1:]:
            row_index = _find_row_of_value(row_data, parent)
            if row_index < 0:
                return QModelIndex()  # rly? why?
            row_data = row_data.children[row_index]

        return self.createIndex(row_index, 0, row_data.id)

    def _updateRow(self, row_data, index, new_value=None, new_label=None):
        # reinitialize row identified by given model index with new value
        if new_value is None:
            if self._cursor is not None:
                try:
                    template = row_data.instantiatedType.template
                    context = template.typeManager.prepareContext(row_data.instantiatedType.context,
                                                                  template, self._cursor)
                    new_value = row_data.instantiatedType.template.decode(context)
                except datatypes.DecodeError as err:
                    new_value = err.value
            else:
                new_value = datatypes.Value()

        old_children = row_data.children[:]
        children_to_update = row_data.children

        old_children_names = [rd.label for rd in old_children]
        new_children_names = list(new_value.members.keys())

        # find differences
        try:
            matcher = difflib.SequenceMatcher(None, old_children_names, new_children_names, autojunk=False)
        except TypeError:
            # in Python <3.2 there is no autojunk parameter
            matcher = difflib.SequenceMatcher(None, old_children_names, new_children_names)

        # now process differences between old and new members
        diff = 0
        for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
            if opcode == 'equal' or opcode == 'replace':
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    member_value = new_value.members[new_children_names[j]]
                    self._updateRow(children_to_update[i + diff], index.child(i + diff, 0), member_value,
                                    new_children_names[j])
            elif opcode == 'insert':
                self.beginInsertRows(index, i1 + diff, i1 + diff + j2 - j1 - 1)
                for j in range(j1, j2):
                    child_row_data = self._buildRowData(new_value, new_children_names[j])
                    children_to_update.insert(i1 + diff + j - j1, child_row_data)
                    self._rowDataDict[child_row_data.id] = child_row_data
                self.endInsertRows()
                diff += j2 - j1
            elif opcode == 'delete':
                self.beginRemoveRows(index, i1 + diff, i2 + diff)
                del children_to_update[i1+diff:i2+diff]
                self.endRemoveRows()
                diff -= i2 - i1

        if new_label is not None:
            row_data.label = new_label
        row_data.value = new_value
        daddy_index = index.parent()
        self.dataChanged.emit(index.sibling(index.row(), 0), index.sibling(index.row(),
                                                                           self.columnCount(daddy_index) - 1))

    def _buildRowData(self, parent_value, member_name):
        row_value = parent_value.members[member_name]
        rd = self.RowData(row_value.instantiatedType, member_name)
        rd.value = row_value
        rd.id = self._lastRowDataId + 1
        self._lastRowDataId += 1
        for child_member_name in row_value.members:
            self._buildRowData(row_value, child_member_name)
        return rd

    def _getType(self, t):
        """Transforms type argument given to methods to InstantiatedType object. Possible arguments are AbstractTemplate
        (empty context will be used) or template name (global type manager and empty context will be used)
        """
        if isinstance(t, datatypes.InstantiatedType):
            return t
        elif isinstance(t, datatypes.AbstractTemplate):
            return datatypes.InstantiatedType(t, datatypes.InstantiateContext())
        elif isinstance(t, str):
            t = datatypes.globalTypeManager().getTemplate(t)
            return datatypes.InstantiatedType(t, datatypes.InstantiateContext())
        else:
            raise ValueError('object of type {0} is not type, template or template name'.format(type(t)))

    def _rowDataFromIndex(self, index):
        return self._rowDataDict.get(index.internalId()) if index.isValid() else None

    _trans_dict = {'\x00': '\\0', '\x07': '\\a', '\x08': '\\b', '\x09': '\\t', '\x0a': '\\n', '\x0b': '\\v',
                   '\x0c': '\\f', '\x0d': '\\r', '\x1b': '\\e', '\x7f': '\\x7f', '\u2028': '\\u2028',
                   '\u2029': '\\u2029'}
    for x in range(1, 32):
        if x not in _trans_dict:
            _trans_dict[chr(x)] = '\\x' + hex(x)[2:]

    _sanitize_trans_table = str.maketrans(_trans_dict)

    @staticmethod
    def _sanitizeString(text):
        return text.translate(InspectorModel._sanitize_trans_table)


class InspectorWidget(QWidget):
    def __init__(self, parent):
        QWidget.__init__(self, parent)

        self.inspectorModel = InspectorModel()

        self.inspectorView = QTreeView(self)
        self.inspectorView.setModel(self.inspectorModel)
        self.inspectorView.setAlternatingRowColors(True)

        def crb(icon_path, tooltip, slot):
            btn = QToolButton(self)
            btn.setIcon(QIcon(icon_path))
            btn.setToolTip(utils.tr(tooltip))
            btn.clicked.connect(slot)
            return btn

        self.btnAddType = crb(':/main/images/plus.png', 'Add type', self._addType)
        self.btnEditType = crb(':/main/images/pencil.png', 'Edit selected type', self._editType)
        self.btnRemoveType = crb(':/main/images/minus.png', 'Remove selected type', self._removeType)
        self.btnExpandAll = crb(':/main/images/expand-all16.png', 'Expand all', self.inspectorView.expandAll)
        self.btnCollapseAll = crb(':/main/images/collapse-all16.png', 'Collapse all', self.inspectorView.collapseAll)

        tool_layout = QHBoxLayout()
        for btn in (self.btnAddType, self.btnEditType, self.btnRemoveType):
            btn.setAutoRaise(True)
            tool_layout.addWidget(btn)
        tool_layout.addStretch()
        for btn in (self.btnExpandAll, self.btnCollapseAll):
            btn.setAutoRaise(True)
            tool_layout.addWidget(btn)

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
            new_index = self.inspectorModel.appendType(dlg.instantiated, dlg.description)
            if new_index.isValid():
                self.inspectorView.setCurrentIndex(new_index)

    def _editType(self):
        c_index = self.inspectorView.currentIndex()
        if c_index.isValid() and not c_index.parent().isValid():
            dlg = TypeReplaceDialog(self, c_index.data(InspectorModel.InstantiatedRole),
                                    c_index.data(InspectorModel.LabelRole))
            if dlg.exec_() == TypeReplaceDialog.Accepted:
                self.inspectorModel.setTypeAtRow(c_index.row(), dlg.instantiated, dlg.description)

    def _removeType(self):
        c_index = self.inspectorView.currentIndex()
        if c_index.isValid() and not c_index.parent().isValid():
            self.inspectorModel.removeTypeAtRow(c_index.row())


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
