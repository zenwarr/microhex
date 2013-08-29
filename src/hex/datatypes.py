import string
import struct
import collections
import itertools
import ctypes
import sys
import copy
import hex.utils as utils
import hex.encodings as encodings
from PyQt4.QtCore import QAbstractItemModel, QModelIndex, Qt, pyqtSignal
from PyQt4.QtGui import QWidget, QComboBox, QFormLayout, QSpinBox, QTreeView, QVBoxLayout, QIcon, QLineEdit, QFrame


class TemplateNotFoundError(Exception):
    pass


class DecodeError(Exception):
    pass


LittleEndian, BigEndian = range(2)


class Value(object):
    StatusInvalid, StatusWarning, StatusCorrect = range(3)
    FormatData, FormatDecoded, FormatText, FormatAlternativeText, FormatComment, FormatColor = range(6)

    def __init__(self):
        self.instantiatedType = None
        self.bufferRange = None
        self.decodeStatus = self.StatusInvalid
        self.decodeStatusText = ''
        self.comment = ''
        self.alternativeText = ''
        self.members = collections.OrderedDict()
        self.parentValue = None

        self._cachedBufferData = b''
        self._decodedValue = None

    def data(self, fmt=FormatDecoded):
        if fmt == self.FormatData and self._cachedBufferData:
            return self._cachedBufferData
        elif fmt == self.FormatDecoded and self._decodedValue is not None:
            return self._decodedValue
        elif fmt == self.FormatText:
            return str(self._decodedValue) if self._decodedValue is not None else ''
        elif fmt == self.FormatAlternativeText:
            return self.alternativeText
        elif fmt == self.FormatComment:
            return self.comment

    @property
    def decodedValue(self):
        return self.data()

    @property
    def valid(self):
        return self.bufferRange is not None and self.decodeStatus != self.StatusInvalid

    @property
    def isComplex(self):
        return bool(self.members)

    @property
    def bufferData(self):
        if self._cachedBufferData:
            return self._cachedBufferData
        elif self.bufferRange is not None and self.bufferRange.valid:
            return self.bufferRange.document.read(self.bufferRange.startPosition, self.bufferRange.size)
        else:
            return b''

    @staticmethod
    def buildValue(instantiated_type, buffer_range, decoded):
        result = Value()
        result.instantiatedType = instantiated_type
        result.bufferRange = buffer_range
        result._decodedValue = decoded
        result.decodeStatus = Value.StatusCorrect
        return result

    def getMemberValue(self, name):
        if '.' not in name:
            return self.members.get(name, None)
        else:
            member_value = self.members.get(name[:name.index('.')])
            if member_value is not None:
                return member_value.getMemberValue(name[name.index('.') + 1:])

    def hasMember(self, name):
        if '.' not in name:
            return name in self.members
        else:
            member_value = self.members.get(name[:name.index('.')])
            return member_value is not None and member_value.hasMember(name[name.index('.') + 1:])

    def getFullMemberName(self):
        if self.parentValue is not None:
            name = utils.first(key for key, value in self.parentValue.members.items() if value is self)
            assert(name is not None)
            parent_name = self.parentValue.getFullMemberName()
            return parent_name + '.' + name if parent_name else name
        return ''


class AbstractTemplate:
    def __init__(self, real_name, adjustable_context_properties=None):
        self.realName = real_name
        self.qualifiedName = ''
        self.typeManager = None
        self.defaultAlignHint = 1
        self.adjustableContextProperties = {'endianess': int}
        if adjustable_context_properties is not None:
            self.adjustableContextProperties.update(adjustable_context_properties)
        self.defaultsContext = InstantiateContext()

    def setContextDefaults(self, context):
        context.setDefaultsFromContext(self.defaultsContext)

    def decode(self, context) -> Value:
        raise NotImplementedError()

    @property
    def fixedSize(self):
        return 0

    #def write(self, context, value, write_method):
    #    raise NotImplementedError()

    def createConfigWidget(self, parent):
        pass

    def _cloneTo(self, obj):
        utils.deepCopyAttrs(self, obj, ('realName', 'qualifiedName', 'defaultAlignHint', 'adjustableContextProperties',
                                        'defaultsContext'))

    def clone(self):
        cloned = type(self)()
        self._cloneTo(cloned)
        return cloned

class InstantiatedType:
    def __init__(self, template, context):
        self.template = template
        self.context = context


class InstantiateContext(object):
    def __init__(self):
        self.cursor = None
        self.endianess = LittleEndian
        self.alignHint = 0

    def setDefaults(self, **defaults):
        for key in defaults.keys():
            if not hasattr(self, key):
                setattr(self, key, defaults[key])

    def setDefaultsFromContext(self, def_context):
        for attr_name in dir(def_context):
            if not attr_name.startswith('_') and not utils.isCallable(getattr(def_context, attr_name)):
                if not hasattr(self, attr_name):
                    setattr(self, attr_name, getattr(def_context, attr_name))

    @staticmethod
    def buildContext(**params):
        context = InstantiateContext()
        for param_name, param_value in params.items():
            setattr(context, param_name, param_value)
        return context

    def get(self, name, default=None):
        return getattr(self, name) if hasattr(self, name) else default


class PlatformProfile:
    """Platform profile provides typedefs for fixed-size integers that are specific for platform as well as some
    other information (endianess)
    """
    def __init__(self, name):
        self.name = name  # can be used as namespace name for platform-specific typedef, so should be valid ns name
        self.primitiveTypes = dict()  # typedef name for primitive type: (real type name, alignment_hint)
        self.endianess = LittleEndian


class AbstractFormatTypeTemplate(AbstractTemplate):
    """Type based on primitive types parsing from struct module. These types are always fixed size. Subclasses should
    provide implementation of fixedSize and _formatString properties for this class to work.
    """

    def decode(self, context):
        try:
            assert(self.fixedSize > 0)
            data_to_decode = context.cursor.read(0, self.fixedSize)
        except IndexError:
            raise ValueError(utils.tr('failed to decode value: no enough data available'))

        try:
            unpacked = struct.unpack(self._getFormatString(context), data_to_decode)
            if unpacked is not None:
                instantiated = InstantiatedType(self, context)
                result = Value.buildValue(instantiated, context.cursor.bufferRange(0, self.fixedSize), unpacked[0])
                result._cachedBufferData = data_to_decode
                return result
            else:
                return Value()
        except struct.error as err:
            raise ValueError(utils.tr('failed to decode value: {0}').format(err))

    def _getFormatString(self, context):
        raise NotImplementedError()

    # def encode(self, value, cursor=None):
    #     if not self.canEncode(value):
    #         return
    #
    #     if isinstance(value, Value):
    #         value = value.decodedValue
    #     if not isinstance(value, Value) and self.canEncode(value):
    #         try:
    #             return struct.pack(self._formatString, value)
    #         except struct.error as err:
    #             err = str(err)
    #
    #         raise ValueError(utils.tr('failed to encode value: {0}').format(err))


class AbstractIntegerTemplate(AbstractFormatTypeTemplate):
    _WidthFormatDict = {1: 'b', 2: 'h', 4: 'i', 8: 'q'}

    def __init__(self, real_name, width, signed):
        if width not in self._WidthFormatDict:
            raise ValueError(utils.tr('integers of width {0} are not supported').format(width))
        AbstractFormatTypeTemplate.__init__(self, real_name)
        self._width = width
        self._signed = signed
        self.defaultAlignHint = width

    @property
    def fixedSize(self):
        return self._width

    @property
    def maximal(self):
        return (256 ** self._width // (2 if self._signed else 1)) - 1

    @property
    def minimal(self):
        return -self.maximal - 1 if self._signed else 0

    def _getFormatString(self, context):
        width_format = self._WidthFormatDict[self._width]
        return ('<' if context.endianess == LittleEndian else '>') + (width_format if self._signed else
                                                                      width_format.upper())

    def createConfigWidget(self, parent):
        return OnlyEndianessConfigWidget(parent, self)

    # def canEncode(self, value):
    #     if isinstance(value, Value):
    #         value = value.decodedValue
    #     return isinstance(value, int) and self.minimal <= value <= self.maximal
    #
    # def parseString(self, text):
    #     try:
    #         return int(text)
    #     except ValueError:
    #         return None


class FloatTemplate(AbstractFormatTypeTemplate):
    @property
    def fixedSize(self):
        return 4

    def __init__(self):
        AbstractFormatTypeTemplate.__init__(self, 'float')
        self.defaultAlignHint = 4

    def _getFormatString(self, context):
        return ('<' if context.endianess == LittleEndian else '>') + 'f'

    def createConfigWidget(self, parent):
        return OnlyEndianessConfigWidget(parent, self)

    # def canEncode(self, value):
    #     # unfortunately, struct.pack does not raises any exception when converting too large Python float to
    #     # float and silently replaces its value with inf (or -inf). So encode/decode value and see if it was
    #     # converted to inf.
    #     if isinstance(value, Value):
    #         value = value.decodedValue
    #     if not isinstance(value, float):
    #         return False
    #     if math.isfinite(value):
    #         try:
    #             return math.isfinite(struct.unpack(self._formatString, struct.pack(self._formatString, value)))
    #         except struct.error:
    #             return False
    #     return True
    #
    # def parseString(self, text):
    #     try:
    #         return float(text)
    #     except ValueError:
    #         return None


class DoubleTemplate(AbstractFormatTypeTemplate):
    @property
    def fixedSize(self):
        return 8

    def __init__(self):
        AbstractFormatTypeTemplate.__init__(self, 'double')
        self.defaultAlignHint = 8

    def _getFormatString(self, context):
        return ('<' if context.endianess == LittleEndian else '>') + 'd'

    def createConfigWidget(self, parent):
        return OnlyEndianessConfigWidget(parent, self)

    # def canEncode(self, value):
    #     if isinstance(value, Value):
    #         value = value.decodedValue
    #     return isinstance(value, float)


class Structure(AbstractTemplate):
    """Represents set of fields with different names, which values are decoded sequentially to get resulting value.
    """

    class Field:
        def __init__(self, name, template, type_context=None, align_hint=0):
            """:align_hint: == 0 - automatic alignment
               :align_hint: == 1 - no alignment
               :template: - should be of AbstractTemplate class.
            """
            self.name = name
            self.template = template
            self.typeContext = type_context or InstantiateContext()
            if align_hint > 0:
                self.typeContext.alignHint = align_hint

        def setContextPropertyFromValue(self, prop_name, value):
            return self.setContextPropertyFromRawValue(prop_name, value.decodedValue)

        def setContextPropertyFromRawValue(self, prop_name, value):
            """Set one of attributes enumerated in template adjustableContextProperties property. Does type checking.
            Can set nested properties looking for sub-properties in context fields.
            """
            if '.' not in prop_name:
                # set property of this context - check if we have adjustable property with this name and
                # check value type.
                if prop_name not in self.template.adjustableContextProperties:
                    raise ValueError(utils.tr('{0} is not an adjustable context property').format(prop_name))
                elif not isinstance(value, self.template.adjustableContextProperties[prop_name]):
                    raise ValueError(utils.tr('while updating context property {0}: type mismatch').format(prop_name))
                if not hasattr(self.typeContext, prop_name) or getattr(self.typeContext, prop_name) != value:
                    setattr(self.typeContext, prop_name, value)
                    return True
            else:
                # we must set property of field context. Find field with corresponding name and recursively
                # set property for it.
                subfield_name = prop_name[:prop_name.index('.')]
                my_fields = self.typeContext.fields if hasattr(self.typeContext, 'fields') else tuple()
                field = utils.first(field for field in my_fields if field.name == subfield_name)
                if field is None:
                    raise ValueError(utils.tr('while updating property {0}: no field named {1}').format(prop_name,
                                                                                                        subfield_name))
                return field.setContextPropertyFromRawValue(prop_name[prop_name.index('.') + 1:], value)
            return False

        def hasProperty(self, prop_name):
            if '.' not in prop_name:
                return prop_name in self.template.adjustableContextProperties
            else:
                if hasattr(self.typeContext, 'fields'):
                    subfield_name = prop_name[:prop_name.index('.')]
                    subfield = utils.first(field for field in self.typeContext.fields if field.name == subfield_name)
                    if subfield is not None:
                        return subfield.hasProperty(prop_name[prop_name.index('.')+1:])
                return False

    class Link:
        def __init__(self, source, destination):
            self.source = source
            self.destination = destination

    class InvalidateField(Exception):
        def __init__(self, updated_link_impl, new_value, field_context):
            self.updatedLinkImpl = updated_link_impl
            self.newValue = new_value
            self.fieldContext = field_context

    class LinkImpl:
        """This is internal class used to update links. After parsing a field, structure calls LinkImpl.update for
        each LinkImpl that passed in context 'linkImpl' attribute having sourceFieldName attribute value equal to
        parsed field name.
        """
        def __init__(self, source_field_name, dependent_field, dependent_property, current_field, keeping_context):
            self.sourceFieldName = source_field_name  # name of field this link depends on
            self.dependentField = dependent_field  # Field which property should be updated. Note that this
                                                   # field is in keeping context, not context of structure being parsed.
            self.dependentProperty = dependent_property  # name of property that should be updated
            self.currentField = current_field  # field in keeping context being currently parsing
            self.keepingContext = keeping_context

        @property
        def dependentFieldIndex(self):
            return utils.indexOf(self.keepingContext.fields, lambda field: field is self.dependentField)

        @property
        def currentFieldIndex(self):
            return utils.indexOf(self.keepingContext.fields, lambda field: field is self.currentField)

        def update(self, new_value, current_context):
            assert(self.keepingContext is not current_context)
            if self.dependentField.setContextPropertyFromValue(self.dependentProperty, new_value):
                if self.dependentFieldIndex <= self.currentFieldIndex:
                    raise Structure.InvalidateField(self, new_value, current_context)

    def __init__(self):
        AbstractTemplate.__init__(self, 'struct')

    def decode(self, context):
        context.setDefaults(fields=list(), links=list(), linkImpls=list())
        result_value = Value.buildValue(InstantiatedType(self, context), None, None)

        # what about links? Once client code tries to decode structure, it passes context with list of Structure.Link
        # objects in 'links' attribute. Before decoding field, structure code looks for links which sourceFieldName
        # starts with field_name + '.'. For each of them it creates corresponding LinkImpl object and adds it to
        # field context 'linkImpls' list. Also it looks for LinkImpls in context 'linkImpls' attribute value and
        # adds new LinkImpls based on this LinkImpls to field context. Structure code will raise decode exception
        # if it founds links referring to sub-fields of non-structure fields. Then structure decodes field value.
        # Next step is to update links depending on this value. Structure code looks for LinkImpls in context
        # 'linkImpls' list and for ones which sourceFieldName matches decoded field name, calls LinkImpl.update.
        # This method set property value for linked context, and raises InvalidateField exception if parent
        # structure should update some fields.
        #
        #
        # When decoding fields, structure adds list of Structure.LinkImpl objects
        # to field context. This list contains links that depend on this field fields. For example, if structure
        # context has link between 'a.b' and 'c.prop', context constructed for decoding field 'a' will contain
        # LinkImpl with sourceFieldName == 'b'. When child structure decodes value for field 'b', it calls
        # LinkImpl.update, which updates context property with name 'prop' for parent structure 'c' field. If
        # value for 'c' field was already parsed by parent structure ,

        cursor = context.cursor.clone()

        stored_cursor_positions = list()
        field_index = 0
        while field_index < len(context.fields):
            try:
                field = context.fields[field_index]
                if field_index < len(stored_cursor_positions):
                    cursor.position = stored_cursor_positions[field_index]

                # store cursor position for this field. We will use it when rolling back to this field on processing
                # back links.
                if field_index >= len(stored_cursor_positions):
                    stored_cursor_positions.append(cursor.position)
                else:
                    stored_cursor_positions[field_index] = cursor.position
                    del stored_cursor_positions[field_index+1:]

                # resolve template
                if isinstance(field.template, str):
                    template = self.typeManager.getTemplateChecked(field.template)
                    q_name = field.template
                else:
                    template = field.template
                    q_name = None

                if template is None:
                    raise ValueError(utils.tr('no template for field {0}').format(field.name))

                type_manager = context.typeManager or globalTypeManager()
                field_context = type_manager.prepareContext(field.typeContext, template, cursor, q_name)

                # determine start position for this field respecting field alignment.
                field_align_hint = field_context.alignHint if field_context.alignHint > 0 else template.defaultAlignHint
                if field_align_hint > 1 and (cursor.position - context.cursor.position) % field_align_hint:
                    cursor.advance(field_align_hint - ((cursor.position - context.cursor.position) % field_align_hint))

                # build list of LinkImpls for field context
                # first collect it from our context links
                for link in context.links:
                    if link.source.startswith(field.name + '.'):
                        dep_field_name = link.destination[:link.destination.index('.')]
                        if not isinstance(field.template, Structure):
                            raise ValueError(utils.tr('while processing link {0}: {1} is not a structure')
                                                    .format(link.source, dep_field_name))

                        field_context.setDefaults(linkImpls=list())

                        # create corresponding LinkImpl and add it
                        dep_field = utils.first(field for field in context.fields if field.name == dep_field_name)
                        dep_prop = link.destination[link.destination.index('.') + 1:]
                        impl = self.LinkImpl(link.source[link.source.index('.') + 1:], dep_field, dep_prop, field, context)
                        field_context.linkImpls.append(impl)

                # second, find LinkImpls that should be transferred to field
                for link_impl in context.linkImpls:
                    if link_impl.sourceFieldName.startswith(field.name + '.'):
                        field_context.setDefaults(linkImpls=list())

                        # copy this impl, but adjust sourceFieldName - remove field name
                        cloned_impl = copy.copy(link_impl)
                        cloned_impl.sourceFieldName = link_impl.sourceFieldName[link_impl.sourceFieldName.index('.')+1:]
                        field_context.linkImpls.append(cloned_impl)

                # decode field value
                field_value = template.decode(field_context)
                field_value.parentValue = result_value

                impls = context.linkImpls[:]
                # find links that should be updated and add them to impls list
                for link in context.links:
                    if link.source == field.name:
                        dep_field_name = link.destination[:link.destination.index('.')]
                        dep_field = utils.first(field for field in context.fields if field.name == dep_field_name)
                        dep_prop = link.destination[link.destination.index('.') + 1:]
                        impls.append(self.LinkImpl(link.source, dep_field, dep_prop, field, context))

                # now find links that should be updated with decoded value of this field
                for link_impl in impls:
                    if link_impl.sourceFieldName == field.name:
                        link_impl.update(field_value, field_context)

                result_value.members[field.name] = field_value

                cursor.advance(field_value.bufferRange.size)
                field_index += 1
            except self.InvalidateField as inv_field:
                if inv_field.updatedLinkImpl.keepingContext is context:
                    field_index = inv_field.updatedLinkImpl.dependentFieldIndex
                    continue
                else:
                    raise

        result_value.bufferRange = context.cursor.bufferRange(0, cursor.position - context.cursor.position)
        return result_value


class StructureContextBuilder:
    def __init__(self, type_manager=None):
        self.typeManager = type_manager or globalTypeManager()
        self.context = InstantiateContext.buildContext(fields=list(), links=list())

    def addField(self, name, template, context=None, align_hint=0):
        if isinstance(template, str):
            template = self.typeManager.getTemplateChecked(template)
        elif template is None:
            raise TypeError('template not found')
        self.context.fields.append(Structure.Field(name, template, context, align_hint))

    def addLink(self, src, dst):
        self.context.links.append(Structure.Link(src, dst))


class AbstractTypeConfigWidget(QWidget):
    descriptionChanged = pyqtSignal()

    def __init__(self, parent, template):
        QWidget.__init__(self, parent)
        self.template = template

    def initFromContext(self, context):
        pass

    def createContext(self):
        raise NotImplementedError()

    @property
    def description(self):
        return None


class OnlyEndianessConfigWidget(AbstractTypeConfigWidget):
    def __init__(self, parent, template):
        AbstractTypeConfigWidget.__init__(self, parent, template)

        self.cmbEndianess = QComboBox(self)
        self.cmbEndianess.addItem(utils.tr('Little endian'), LittleEndian)
        self.cmbEndianess.addItem(utils.tr('Big endian'), BigEndian)

        self.setLayout(QFormLayout())
        self.layout().addRow(utils.tr('Endianess:'), self.cmbEndianess)

    def initFromContext(self, context):
        self.cmbEndianess.setCurrentIndex(int(context.endianess == BigEndian))

    def createContext(self):
        context = InstantiateContext()
        context.endianess = LittleEndian if self.cmbEndianess.currentIndex() == 0 else BigEndian
        return context


class ZeroStringConfigWidget(AbstractTypeConfigWidget):
    descriptionChanged = pyqtSignal(str)

    def __init__(self, parent, template):
        AbstractTypeConfigWidget.__init__(self, parent, template)

        self.cmbEncoding = encodings.EncodingsCombo(self, 'utf-8')
        self.cmbEncoding.encodingNameChanged.connect(self._onEncodingChanged)
        self.spnLimit = QSpinBox(self)
        self.spnLimit.setMaximum(10000)
        self.spnLimit.setValue(self.spnLimit.maximum())

        self.setLayout(QFormLayout())
        self.layout().addRow(utils.tr('Encoding:'), self.cmbEncoding)
        self.layout().addRow(utils.tr('Length limit (chars):'), self.spnLimit)

    def initFromContext(self, context):
        self.cmbEncoding.encoding = context.get('encoding', 'utf-8')
        self.spnLimit.setValue(context.get('limit', 10000))

    def createContext(self):
        context = InstantiateContext()
        context.encoding = self.cmbEncoding.encoding
        context.limit = self.spnLimit.value()
        return context

    @property
    def description(self):
        return 'zero_string [{0}]'.format(self.cmbEncoding.encodingName)

    def _onEncodingChanged(self):
        self.descriptionChanged.emit(self.description)


class ZeroStringTemplate(AbstractTemplate):
    def __init__(self):
        AbstractTemplate.__init__(self, 'zero_string', dict(encoding=str, limit=int))

    def setContextDefaults(self, context):
        context.setDefaults(encoding=encodings.getCodec('utf-8'), limit=10000)
        AbstractTemplate.setContextDefaults(self, context)

    @property
    def fixedSize(self):
        return 0

    def decode(self, context):
        cloned_cursor = context.cursor.clone()
        if isinstance(context.encoding, encodings.AbstractCodec):
            encoding = context.encoding
        else:
            encoding = encodings.getCodec(context.encoding)
        if encoding is None:
            raise ValueError('no encoding found')

        bytes_parsed = 0
        parsed_chars = list()
        with cloned_cursor.activate():
            while cloned_cursor.isAtValidPosition:
                if context.limit >= 0 and len(parsed_chars) >= context.limit:
                    break

                try:
                    char_data = encoding.getCharacterData(cloned_cursor)
                except encodings.EncodingError:
                    raise ValueError()

                bytes_parsed += char_data.bufferRange.size
                if char_data.unicode == '\u0000':
                    break
                parsed_chars.append(char_data.unicode)

                cloned_cursor.advance(char_data.bufferRange.size)
            else:
                raise ValueError('unterminated zero_string')

        result = Value.buildValue(self, ''.join(parsed_chars), ''.join(parsed_chars))
        result.bufferRange = context.cursor.bufferRange(0, bytes_parsed)
        return result

    def createConfigWidget(self, parent):
        return ZeroStringConfigWidget(parent, self)


class FixedStringTemplate(AbstractTemplate):
    def __init__(self):
        AbstractTemplate.__init__(self, 'fixed_string', dict(size=int, encoding=str))

    def setContextDefaults(self, context):
        context.setDefaults(encoding=encodings.getCodec('utf-8'), size=0)
        AbstractTemplate.setContextDefaults(self, context)

    @property
    def fixedSize(self):
        return 0

    def decode(self, context):
        cloned_cursor = context.cursor.limited(context.size)
        if isinstance(context.encoding, encodings.AbstractCodec):
            encoding = context.encoding
        else:
            encoding = encodings.getCodec(context.encoding)
        if encoding is None:
            raise ValueError(utils.tr('no encoding {0} found').format(context.encoding))

        decoded_chars = list()
        while cloned_cursor.position - context.cursor.position < context.size:
            try:
                char_data = encoding.getCharacterData(cloned_cursor)
                decoded_chars.append(char_data.unicode)
                cloned_cursor.advance(char_data.bufferRange.size)
            except encodings.EncodingError:
                raise ValueError()

        value = Value.buildValue(InstantiatedType(self, context),
                                 context.cursor.bufferRange(0, cloned_cursor.position - context.cursor.position),
                                 ''.join(decoded_chars))
        return value

    def createConfigWidget(self, parent):
        return FixedStringConfigWidget(parent, self)


class FixedStringConfigWidget(AbstractTypeConfigWidget):
    descriptionChanged = pyqtSignal(str)

    def __init__(self, parent, template):
        AbstractTypeConfigWidget.__init__(self, parent, template)

        self.cmbEncoding = encodings.EncodingsCombo(self, 'utf-8')
        self.cmbEncoding.encodingNameChanged.connect(self._onEncodingChanged)
        self.spnSize = QSpinBox(self)
        self.spnSize.setMaximum(20)
        self.spnSize.setValue(self.spnSize.maximum())

        self.setLayout(QFormLayout())
        self.layout().addRow(utils.tr('Encoding:'), self.cmbEncoding)
        self.layout().addRow(utils.tr('Size (bytes):'), self.spnSize)

    def initFromContext(self, context):
        self.cmbEncoding.encoding = context.get('encoding', 'utf-8')
        self.spnSize.setValue(context.get('limit', 20))

    def createContext(self):
        context = InstantiateContext()
        context.encoding = self.cmbEncoding.encoding
        context.size = self.spnSize.value()
        return context

    @property
    def description(self):
        return 'fixed_string [{0}]'.format(self.cmbEncoding.encodingName)

    def _onEncodingChanged(self):
        self.descriptionChanged.emit(self.description)


class TypesNamespace(object):
    """Groups type templates and namespaces together.
    """

    def __init__(self, name, parent_namespace):
        self.name = name
        self.parentNamespace = parent_namespace
        self.members = collections.OrderedDict()

    def enumerate(self):
        for member in self.members.values():
            yield member


class TypeManager:
    def __init__(self, profile=None):
        self.rootNamespace = TypesNamespace('', None)
        self.platformProfile = profile or self.getPlatformProfile()

    def install(self, name, template):
        """Installs type template to this type manager. Name should be fully qualified (no shortcuts like '.name'
        allowed)
        """
        if not name or not isinstance(template, AbstractTemplate):
            raise ValueError(utils.tr('failed to install type template'))

        name_parts = name.split('.')
        if len(name_parts) == 1:
            raise ValueError(utils.tr('type templates cannot be installed to root namespace'))

        if not self.isValidName(name_parts[-1]):
            raise ValueError(utils.tr('failed to install type template: name {0} is invalid').format(name_parts[-1]))

        ns = self._createNamespace('.'.join(name_parts[:-1]))
        if name_parts[-1] in ns.members:
            # we cannot pollute namespace with unused namespace - if name reserved, namespace already in use
            raise ValueError(utils.tr('cannot install type template {0} - name already reserved').format(name))
        ns.members[name_parts[-1]] = template
        template.typeManager = self
        template.qualifiedName = name

    def getNamespace(self, namespace_name) -> TypesNamespace:
        if not namespace_name:
            return self.rootNamespace
        current_namespace = self.rootNamespace
        for name_part in namespace_name.split('.'):
            current_namespace = current_namespace.members.get(name_part)
            if current_namespace is None or not isinstance(current_namespace, TypesNamespace):
                return None
        return current_namespace

    def getTemplate(self, type_name) -> AbstractTemplate:
        """There are three forms in which type name can be specified:
            - with fully qualified namespaces (namespace.nested.type)
            - with leading dot - in this case type will be searched in builtins namespace (.type = builtins.type)
            - plain type name without namespaces - type will be searched in builtins namespace too
              (type = builtins.type). With this method you cannot specify type that is in namespace inside builtins.
        """
        namespace_name, unqualified_type_name = self.splitQualifiedName(self.normalizeName(type_name))
        namespace = self.getNamespace(namespace_name)
        if namespace is not None:
            template = namespace.members.get(unqualified_type_name)
            if isinstance(template, AbstractTemplate):
                return template

    def getTemplateChecked(self, type_name):
        template = self.getTemplate(type_name)
        if template is None:
            raise TemplateNotFoundError(self.normalizeName(type_name))
        return template

    def decode(self, type_name, cursor, context=None) -> Value:
        template = self.getTemplateChecked(type_name)
        context = self.prepareContext(context, template, cursor, type_name)
        return template.decode(context)

    #def write(self, type_name, cursor, value, write_method, context=None) -> None:
    #    template = self.getTemplateChecked(type_name)
    #    context = self.prepareContext(context, template, cursor, type_name)
    #    return template.write(context, value, write_method)

    @staticmethod
    def normalizeName(name):
        """Converts type name to fully qualified form. See getDataType docstring for description of possible
        type name forms.
        """
        if '.' not in name:
            return 'builtins.' + name
        elif name.startswith('.'):
            return 'builtins' + name
        return name

    def createConfigWidget(self, parent, type_name) -> AbstractTypeConfigWidget:
        """Creates widget to configure given data type. Use AbstractDataType.createConfigWidget to create widget
        that will be initialized with instantiated type parameters.
        """
        return self.getTemplateChecked(type_name).createConfigWidget(parent)

    _allowed_first_chars = string.ascii_letters + '_'
    _allowed_chars = string.ascii_letters + string.digits + '_'

    @staticmethod
    def isValidName(name) -> bool:
        return (isinstance(name, str) and bool(name) and name[0] in TypeManager._allowed_first_chars and
                all(c in TypeManager._allowed_chars for c in name[1:]))

    def _createNamespace(self, namespace_name):
        current_namespace = self.rootNamespace
        for part in namespace_name.split('.'):
            if not self.isValidName(part):
                raise ValueError(utils.tr('invalid namespace name: {0}').format(part))
            if part not in current_namespace.members:
                current_namespace.members[part] = TypesNamespace(part, current_namespace)
            current_namespace = current_namespace.members[part]
            if current_namespace is None or not isinstance(current_namespace, TypesNamespace):
                raise ValueError(utils.tr('{0} is not a namespace').format(current_namespace))
        return current_namespace

    @staticmethod
    def splitQualifiedName(name):
        if '.' in name:
            return name[:name.rindex('.')], name[name.rindex('.') + 1:]
        else:
            return '', name

    def setContextDefaults(self, context):
        context.setDefaults(endianess=self.platformProfile.endianess, platformProfile=self.platformProfile)

    def prepareContext(self, context, template, cursor, qualified_name=None):
        if context is None:
            context = InstantiateContext()
        context.cursor = cursor
        context.typeManager = self
        self.setContextDefaults(context)
        if qualified_name is not None:
            context.setDefaults(qualifiedName=self.normalizeName(qualified_name))
        template.setContextDefaults(context)
        return context

    def installBuiltins(self):
        # build standard integer types
        _int_types_data = (
            ('int8', 1, True), ('uint8', 1, False), ('int16', 2, True), ('uint16', 2, False),
            ('int32', 4, True), ('uint32', 4, False), ('int64', 8, True), ('uint64', 8, False)
        )

        def _createIntTemplate(real_name, int_width, int_signed):
            def type_init(self):
                AbstractIntegerTemplate.__init__(self, real_name, int_width, int_signed)

            return type(real_name.capitalize(), (AbstractIntegerTemplate,), dict(__init__=type_init))()

        for int_type_data in _int_types_data:
            self.install('builtins.' + int_type_data[0], _createIntTemplate(*int_type_data))

        self.install('builtins.float', FloatTemplate())
        self.install('builtins.double', DoubleTemplate())
        self.install('builtins.fixed_string', FixedStringTemplate())
        self.install('builtins.zero_string', ZeroStringTemplate())
        self.install('builtins.struct', Structure())

        # create platform-specific typedefs for integers
        platform = self.platformProfile
        platform_prefix = (platform.name or 'platform') + '.'
        for typedef_name in platform.primitiveTypes:
            base_type = self.getTemplate(platform.primitiveTypes[typedef_name][0])
            if base_type is not None:
                real_type = _createIntTemplate(platform.primitiveTypes[typedef_name][0], base_type._width,
                                               base_type._signed)
                real_type.defaultAlignHint = platform.primitiveTypes[typedef_name][1]
                self.install(platform_prefix + typedef_name, real_type)

    int_ds = {
        ('char', 'c_byte'),  # note that c_char can be unsigned on some platforms
        ('uchar', 'c_ubyte'),
        ('short', 'c_short'),
        ('ushort', 'c_ushort'),
        ('int', 'c_int'),
        ('uint', 'c_int'),
        ('long', 'c_long'),
        ('ulong', 'c_ulong'),
        ('longlong', 'c_longlong'),
        ('ulonglong', 'c_ulonglong')
    }

    @staticmethod
    def getPlatformProfile():
        profile = PlatformProfile('platform')
        for int_d in TypeManager.int_ds:
            # determine width and alignment of corresponding C type
            c_type = getattr(ctypes, int_d[1])
            int_width = ctypes.sizeof(c_type)
            int_alignment = ctypes.alignment(c_type)
            # and find fixed-width builtin int typedef should be mapped to
            real_type_name = ('u' if int_d[0].startswith('u') else '') + 'int' + str(int_width * 8)
            profile.primitiveTypes[int_d[0]] = real_type_name, int_alignment

        profile.endianess = LittleEndian if sys.byteorder == 'little' else BigEndian
        profile.name = 'platform'
        return profile


globalTypeManager = utils.createSingleton(TypeManager)
globalTypeManager().installBuiltins()


class TypeChooserWidget(QWidget):
    """Allows user to choose one type from installed types. Displays tree view where all installed types are displayed
    in a tree (grouped by namespace), and additional widget provided by type where user can adjust parameters
    type will be instantiated with.
    """
    selectedTemplateChanged = pyqtSignal(object, object)  # new_type, old_type

    def __init__(self, parent, type_manager=None, show_description=True):
        QWidget.__init__(self, parent)

        self.typeManager = type_manager or globalTypeManager()
        self.typeConfigWidget = None
        self._selectedTemplate = None
        self._showDescriptionField = show_description
        self._autoDescription = True
        self._descriptionConnector = utils.SignalConnector(descriptionChanged=self._updateDescription)
        self.descriptionSeparator = None
        self.txtDescription = None
        self._descriptionLayout = None

        self.templatesModel = TypesModel(self.typeManager)
        self.templatesView = QTreeView(self)
        self.templatesView.setModel(self.templatesModel)
        self.templatesView.setSelectionBehavior(QTreeView.SelectRows)
        self.templatesView.setSelectionMode(QTreeView.SingleSelection)
        self.templatesView.selectionModel().currentChanged.connect(self._switchTemplate)
        self.templatesView.setHeaderHidden(True)
        self.templatesView.expandAll()

        if self._showDescriptionField:
            self.descriptionSeparator = QFrame()
            self.descriptionSeparator.setFrameShape(QFrame.HLine)
            self.descriptionSeparator.setFrameShadow(QFrame.Sunken)

            self.txtDescription = QLineEdit()
            self.txtDescription.textEdited.connect(self._onDescriptionTextEdited)
            self._descriptionLayout = QFormLayout()
            self._descriptionLayout.addRow(utils.tr('Description'), self.txtDescription)

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.templatesView)

        if self._showDescriptionField:
            self.layout().addWidget(self.descriptionSeparator)
            self.layout().addLayout(self._descriptionLayout)

    @property
    def description(self):
        return self.txtDescription.text()

    @description.setter
    def description(self, new_text):
        self.txtDescription.setText(new_text)
        self._autoDescription = False

    @property
    def showDescriptionField(self):
        return self._showDescriptionField

    def _onDescriptionTextEdited(self):
        self._autoDescription = False

    def _updateDescription(self, new_desc):
        if self._autoDescription:
            self.txtDescription.setText(new_desc)

    def _switchTemplate(self, current):
        """Called each time current template in view is changed, and updates type configuration widget"""
        # remove configuration widget of previous template, if any
        if self.typeConfigWidget is not None:
            self.layout().removeWidget(self.typeConfigWidget)
            self.typeConfigWidget.deleteLater()
            self.typeConfigWidget = None

        old_selected = self._selectedTemplate
        self._selectedTemplate = None
        self.txtDescription.clear()
        self._autoDescription = True

        template = current.data(TypesModel.TemplateRole)
        if template is not None:
            self._selectedTemplate = template
            self.typeConfigWidget = template.createConfigWidget(self)
            if self.typeConfigWidget is not None:
                self.layout().insertWidget(1, self.typeConfigWidget)

                if self._showDescriptionField:
                    if self.typeConfigWidget is not None and hasattr(self.typeConfigWidget, 'description'):
                        self.txtDescription.setText(self.typeConfigWidget.description)
                    else:
                        self.txtDescription.setText(current.data())

        if self._showDescriptionField:
            self.txtDescription.setEnabled(self._selectedTemplate is not None)
            self._descriptionConnector.target = self.typeConfigWidget

        if self._selectedTemplate is not old_selected:
            self.selectedTemplateChanged.emit(self._selectedTemplate, old_selected)

    @property
    def selectedTemplate(self):
        return self._selectedTemplate

    @selectedTemplate.setter
    def selectedTemplate(self, new_template):
        self.templatesView.setCurrentIndex(self.templatesModel.indexFromTemplate(new_template))

    @property
    def context(self):
        if self.selectedTemplate is not None:
            if self.typeConfigWidget is not None:
                return self.typeConfigWidget.createContext()
            else:
                return InstantiateContext()

    @context.setter
    def context(self, new_context):
        if self.typeConfigWidget is not None:
            self.typeConfigWidget.initFromContext(new_context)

    @property
    def instantiated(self):
        return InstantiatedType(self.selectedTemplate, self.context)

    @instantiated.setter
    def instantiated(self, inst):
        self.selectedTemplate = inst.template
        self.context = inst.context


class TypesModel(QAbstractItemModel):
    """Model represents all available types and namespaces in hierarchical structure. First level consist of namespaces
    residing in root namespace.
    """
    TemplateNameRole, TemplateRole = Qt.UserRole + 1, Qt.UserRole + 2

    def __init__(self, type_manager=None):
        QAbstractItemModel.__init__(self)
        self._internalDataCache = list()
        self._typeManager = type_manager or globalTypeManager()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            ns = parent.internalPointer()[1]
            if not isinstance(ns, TypesNamespace):
                return 0
        else:
            ns = self._typeManager.rootNamespace
        return len(ns.members)

    def columnCount(self, parent=QModelIndex()):
        return int(not parent.isValid() or isinstance(parent.internalPointer()[1], TypesNamespace))

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            ns, obj = index.internalPointer()
            if isinstance(obj, TypesNamespace):
                if role == Qt.DisplayRole:
                    return obj.name
                elif role == Qt.DecorationRole:
                    return QIcon(':/main/images/edit-code.png')
            elif obj is not None:
                assert(isinstance(obj, AbstractTemplate))
                if role == Qt.DisplayRole:
                    return TypeManager.splitQualifiedName(obj.qualifiedName)[1]
                elif role == Qt.DecorationRole:
                    return QIcon(':/main/images/type.png')
                elif role == self.TemplateNameRole:
                    return obj.qualifiedName
                elif role == self.TemplateRole:
                    return obj

    def parent(self, index):
        if index.isValid():
            return self.indexFromNamespace(index.internalPointer()[0])
        return QModelIndex()

    def index(self, row, column, parent=QModelIndex()):
        """Internal data of index contains tuple (namespace, object) where :object: is object represented by index
        (TypesNamespace or AbstractDataType) and :namespace: is TypesNamespace containing this object.
        """
        ns = self._typeManager.rootNamespace if not parent.isValid() else parent.internalPointer()[1]
        if ns is not None and 0 <= row < len(ns.members) and column == 0:
            obj = list(ns.members.values())[row]
            return self._createIndex(row, column, (ns, obj))
        return QModelIndex()

    def indexFromNamespace(self, ns):
        if ns is not None and ns.parentNamespace is not None:
            parent_ns = ns.parentNamespace
            row = utils.first(index for member, index in zip(parent_ns.members.values(), itertools.count()) if member is ns)
            if row is not None:
                return self._createIndex(row, 0, (parent_ns, ns))
        return QModelIndex()

    def indexFromTemplate(self, template):
        qual_name = TypeManager.normalizeName(template) if isinstance(template, str) else template.qualifiedName
        c_namespace_name, c_type_name = TypeManager.splitQualifiedName(qual_name)
        c_namespace = self._typeManager.getNamespace(c_namespace_name)
        c_namespace_index = self.indexFromNamespace(c_namespace)
        if c_namespace_index.isValid() and c_type_name in c_namespace.members:
            return self.index(list(c_namespace.members.keys()).index(c_type_name), 0, c_namespace_index)
        return QModelIndex()

    def _createIndex(self, row, column, internal_data):
        # well, we cannot just put another tuple to internalPointer of indexes: Qt internally uses this pointer
        # to compare indexes for equality, and indexes with different pointers are considered different. So we
        # must look for already created tuple with same data. This makes our code slow, but... Another reason for
        # having internal data cache is to keep tuples safe from GC.
        if internal_data in self._internalDataCache:
            internal_data = self._internalDataCache[self._internalDataCache.index(internal_data)]
        else:
            self._internalDataCache.append(internal_data)
        return self.createIndex(row, column, internal_data)
