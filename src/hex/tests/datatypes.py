import hex.datatypes as datatypes
import hex.utils as utils
import unittest
import unittest.mock


class TypeManagementTest(unittest.TestCase):
    class DummyTemplate(datatypes.AbstractTemplate):
        def __init__(self):
            datatypes.AbstractTemplate.__init__(self, 'dummy')

        decode = unittest.mock.Mock()

    def test_get_root_namespace(self):
        manager = datatypes.TypeManager()
        ns = manager.getNamespace('')
        self.assertIsNotNone(ns)
        self.assertEqual(ns.name, '')

    def test_get_unexisting_namespace(self):
        manager = datatypes.TypeManager()
        for name in ('.', '....', 'unexisting', 'name.space'):
            self.assertIsNone(manager.getNamespace(name))

    def test_get_unexisting_namespace_inner(self):
        manager = datatypes.TypeManager()
        self.assertIsNone(manager.getNamespace('unexisting.inner'))

        manager._createNamespace('unexisting')
        self.assertIsNone(manager.getNamespace('unexisting.inner'))

    def test_create_namespace(self):
        manager = datatypes.TypeManager()
        manager._createNamespace('new_ns')
        self.assertIsNotNone(manager.getNamespace('new_ns'))

    def test_create_namespace_inner(self):
        manager = datatypes.TypeManager()
        manager._createNamespace('brand_new_ns.inner')
        self.assertIsNotNone(manager.getNamespace('brand_new_ns.inner'))

    def test_get_unexisting_type(self):
        manager = datatypes.TypeManager()
        for name in ('', 'type', 'type.that.does.not.exist'):
            self.assertIsNone(manager.getTemplate(name))

    def test_install_type(self):
        manager = datatypes.TypeManager()
        template = self.DummyTemplate()
        manager.install('brand.new.namespace.spam', template)
        self.assertIs(manager.getTemplate('brand.new.namespace.spam'), template)

    def test_install_template_with_invalid_name(self):
        manager = datatypes.TypeManager()
        template = self.DummyTemplate()
        for tn in ('.', 'spam', 'пачиму_я_не_магу_песать_паруски', 'foo....spam'):
            self.assertRaises(ValueError, lambda: manager.install(tn, template))

    def test_get_unexisting_template(self):
        manager = datatypes.TypeManager()
        manager._createNamespace('this.is.namespace')
        for tn in ('..', '', 'spam', 'this.is.namespace', 'type.does.not.exist'):
            self.assertIsNone(manager.getTemplate(tn))

    def test_instantiate_not_existed_template(self):
        manager = datatypes.TypeManager()
        self.assertRaises(datatypes.TemplateNotFoundError, lambda: manager.decode('builtins.unexisted', None))

    def test_get_builtins_template(self):
        manager = datatypes.TypeManager()
        manager.install('builtins.templ', self.DummyTemplate())
        self.assertIsNotNone(manager.getTemplate('templ'))
        self.assertIsNotNone(manager.getTemplate('.templ'))

    def test_platform_typedefs(self):
        profile = datatypes.PlatformProfile('my_plat')
        profile.primitiveTypes = {'platform_specific': ('int16', 20)}
        manager = datatypes.TypeManager(profile)
        manager.installBuiltins()
        manager.installPlatform()
        platform_specific = manager.getTemplate('my_plat.platform_specific')
        self.assertIsNotNone(platform_specific)
        self.assertEqual(platform_specific.realName, 'int16')
        self.assertEqual(platform_specific.defaultAlignHint, 20)

    def test_defaulted_template(self):
        manager = datatypes.TypeManager()
        template = self.DummyTemplate()
        template.defaultsContext.defaultField = True
        manager.install('builtins.template', template)
        manager.decode('template', utils.DataCursor(b''))
        self.assertTrue(template.decode.call_args[0][0].defaultField)


class Int8Test(unittest.TestCase):
    manager = datatypes.globalTypeManager()

    def test_decode(self):
        for d in ((b'\x00', 0), (b'\xff', -1), (b'\x7f', 0x7f)):
            cursor = utils.DataCursor(d[0])
            self.assertEqual(self.manager.decode('int8', cursor).decodedValue, d[1])

    def test_decode_zerosize(self):
        cursor = utils.DataCursor(b'')
        self.assertRaises(datatypes.DecodeError, lambda: self.manager.decode('int8', cursor))

    def test_decode_large(self):
        for d in ((b'\x33\x00\n', 0), (b'\x0a\xff\x00', -1), (b'\xff\x7f', 0x7f)):
            cursor = utils.DataCursor(d[0], 1)
            self.assertEqual(self.manager.decode('int8', cursor).decodedValue, d[1])

    #def test_can_encode(self):
    #    for d in ((0, True), (-1, True), (-0x80, True), (-0x81, False), (0x7f, True), (0x80, False)):
    #        self.assertEqual(self.manager.canEncode('int8', d[0]), d[1])

    #def test_encode(self):
    #    for d in ((0, b'\x00'), (-1, b'\xff'), (0x7f, b'\x7f'), (-0x80, b'\x80')):
    #        self.assertEqual(self.manager.encode('int8', d[0]), d[1])

    #def test_encode_invalid(self):
    #    self.assertRaises(ValueError, self.manager.encode('int8', 200))


class UInt16Test(unittest.TestCase):
    manager = datatypes.globalTypeManager()

    def test_decode(self):
        for d in ((b'\x00\x00', 0), (b'\x30\xff', 0xff30), (b'\xff\xff', 0xffff)):
            cursor = utils.DataCursor(d[0])
            self.assertEqual(self.manager.decode('uint16', cursor).decodedValue, d[1])

    def test_decode_be(self):
        context = datatypes.InstantiateContext()
        context.endianess = datatypes.BigEndian
        cursor = utils.DataCursor(b'\x30\xff')
        self.assertEqual(self.manager.decode('uint16', cursor, context).decodedValue, 0x30ff)

    #def test_can_encode(self):
    #    for d in ((100, True), (0, True), (-1, False), (0x10000, False)):
    #        self.assertEqual(self.manager.canEncode('uint16', d[0]), d[1])


class FloatTest(unittest.TestCase):
    manager = datatypes.globalTypeManager()
    epsilon = 0.0001

    def test_decode(self):
        for d in ((b'\xfb\x62\xc7\xe3', -7.356069e21), (b'\xd3\xfb\xc7\x2d', 2.273551e-11)):
            cursor = utils.DataCursor(d[0])
            self.assertTrue(abs(self.manager.decode('float', cursor).decodedValue - d[1]) <= self.epsilon * 1e21)


class ZeroStringTest(unittest.TestCase):
    manager = datatypes.globalTypeManager()

    def test_decode(self):
        d = b'Hello, World!\x00'
        decoded = self.manager.decode('zero_string', utils.DataCursor(d))
        self.assertEqual(decoded.data(), "Hello, World!")
        self.assertEqual(decoded.bufferRange.size, 14)

    def test_decode_zero_size(self):
        decoded = self.manager.decode('zero_string', utils.DataCursor(b'\x00'))
        self.assertEqual(decoded.decodedValue, '')

    def test_decode_unterminated(self):
        decoded = self.manager.decode('zero_string', utils.DataCursor(b'hello'))
        self.assertEqual(decoded.decodeStatus, datatypes.Value.StatusWarning)
        self.assertEqual(decoded.decodedValue, 'hello')

        decoded = self.manager.decode('zero_string', utils.DataCursor(b''))
        self.assertEqual(decoded.decodeStatus, datatypes.Value.StatusWarning)
        self.assertEqual(decoded.decodedValue, '')


class FixedStringTest(unittest.TestCase):
    manager = datatypes.globalTypeManager()

    def test_decode(self):
        d = b'Hello, World!'
        decoded = self.manager.decode('fixed_string', utils.DataCursor(d))
        self.assertEqual((decoded.bufferRange.startPosition, decoded.bufferRange.size, decoded.decodedValue),
                         (0, 0, ''))

        context = datatypes.InstantiateContext.buildContext(size=4)
        decoded = self.manager.decode('fixed_string', utils.DataCursor(d), context)
        self.assertEqual((decoded.bufferRange.startPosition, decoded.bufferRange.size, decoded.decodedValue),
                         (0, 4, 'Hell'))

    def test_decode_short(self):
        context = datatypes.InstantiateContext.buildContext(size=10)
        self.assertRaises(datatypes.DecodeError, lambda: self.manager.decode('fixed_string', utils.DataCursor(b''), context))

    def test_decode_partial(self):
        context = datatypes.InstantiateContext.buildContext(size=4, encoding='utf-16le')
        cursor = utils.DataCursor(b'h\x00i\x00', override_buffer_length=3)
        self.assertRaises(datatypes.DecodeError, lambda: self.manager.decode('fixed_string', cursor, context))


class TypesModelTest(unittest.TestCase):
    class DummyTemplate(datatypes.AbstractTemplate):
        def __init__(self, name):
            datatypes.AbstractTemplate.__init__(self, name)

    typeManager = datatypes.TypeManager()
    typeManager.install('builtins.first', DummyTemplate('first_template'))
    typeManager.install('builtins.second', DummyTemplate('second_template'))
    typeManager.install('builtins.third', DummyTemplate('third_template'))

    def test_row_count(self):
        model = datatypes.TypesModel(self.typeManager)
        self.assertEqual(model.rowCount(), len(self.typeManager.rootNamespace.members))
        self.assertEqual(model.rowCount(model.index(0, 0)), len(self.typeManager.getNamespace('builtins').members))

    def test_internal_data(self):
        model = datatypes.TypesModel(self.typeManager)
        builtins = self.typeManager.getNamespace('builtins')
        self.assertEqual(model.index(0, 0).internalPointer(), (self.typeManager.getNamespace(''), builtins))
        builtins_index = model.index(0, 0, model.index(0, 0))
        self.assertEqual(builtins_index.internalPointer(), (builtins, list(builtins.members.values())[0]))

    def test_data(self):
        model = datatypes.TypesModel(self.typeManager)
        self.assertEqual(model.index(0, 0).data(), 'builtins')
        for j in range(len(self.typeManager.getNamespace('builtins').members)):
            sec_name = list(self.typeManager.getNamespace('builtins').members.keys())[j]
            self.assertEqual(model.index(j, 0, model.index(0, 0)).data(), sec_name)

    def test_column_count(self):
        model = datatypes.TypesModel()
        self.assertEqual(model.columnCount(), 1)
        self.assertEqual(model.columnCount(model.index(0, 0)), 1)
        self.assertEqual(model.columnCount(model.index(0, 0, model.index(0, 0))), 0)

    def test_parent(self):
        model = datatypes.TypesModel()
        self.assertFalse(model.parent(model.index(0, 0)).isValid())
        self.assertTrue(model.parent(model.index(0, 0, model.index(0, 0))).isValid())
        self.assertEqual(model.parent(model.index(0, 0, model.index(0, 0))), model.index(0, 0))


class StructureTest(unittest.TestCase):
    test_profile = datatypes.PlatformProfile('platform')
    typeManager = datatypes.TypeManager(test_profile)
    typeManager.installBuiltins()

    def test_empty_struct(self):
        value = self.typeManager.decode('struct', utils.DataCursor(b''))
        self.assertEqual(value.bufferRange.startPosition, 0)
        self.assertEqual(value.bufferRange.size, 0)
        self.assertIsNone(value.decodedValue)
        self.assertFalse(value.members)

    def test_one_field_struct(self):
        context = datatypes.InstantiateContext()
        context.fields = [datatypes.Structure.Field('a', self.typeManager.getTemplate('uint8'))]
        value = self.typeManager.decode('struct', utils.DataCursor(b'\xfe'), context)
        self.assertEqual(len(value.members), 1)
        self.assertEqual(value.members['a'].decodedValue, 0xfe)

    def test_one_field_struct_auto_resolving_field(self):
        context = datatypes.InstantiateContext()
        context.fields = [datatypes.Structure.Field('a', self.typeManager.getTemplate('uint8'))]
        value = self.typeManager.decode('struct', utils.DataCursor(b'\xfe'), context)
        self.assertEqual(len(value.members), 1)
        self.assertEqual(value.members['a'].decodedValue, 0xfe)

    def test_two_field_structure(self):
        context = datatypes.InstantiateContext()
        context.fields = [
            datatypes.Structure.Field('a', self.typeManager.getTemplate('uint8')),
            datatypes.Structure.Field('b', self.typeManager.getTemplate('zero_string'))
        ]
        value = self.typeManager.decode('struct', utils.DataCursor(b'\xff\xfeIt works!\x00', 1), context)
        self.assertEqual(len(value.members), 2)
        self.assertEqual(value.members['a'].decodedValue, 0xfe)
        self.assertEqual(value.members['b'].decodedValue, 'It works!')
        self.assertEqual(value.bufferRange.startPosition, 1)
        self.assertEqual(value.bufferRange.size, 11)

    def test_custom_context(self):
        context = datatypes.InstantiateContext()
        context.fields = [
            datatypes.Structure.Field('a', self.typeManager.getTemplate('uint8')),
            datatypes.Structure.Field('b', self.typeManager.getTemplate('zero_string'),
                                      datatypes.InstantiateContext.buildContext(encoding='utf-16le'))
        ]
        value = self.typeManager.decode('struct', utils.DataCursor(b'\xfeY\x00e\x00s\x00!\x00\x00\x00'), context)
        self.assertEqual(value.members['b'].decodedValue, 'Yes!')

    def test_field_alignment(self):
        context = datatypes.InstantiateContext()
        context.fields = [
            datatypes.Structure.Field('a', self.typeManager.getTemplate('uint8'), align_hint=1),
            datatypes.Structure.Field('b', self.typeManager.getTemplate('uint8'), align_hint=4)
        ]
        value = self.typeManager.decode('struct', utils.DataCursor(b'\xff\x00\x00\x00\xfe'), context)
        self.assertEqual(value.members['a'].decodedValue, 0xff)
        self.assertEqual(value.members['a'].bufferRange.startPosition, 0)
        self.assertEqual(value.members['a'].bufferRange.size, 1)
        self.assertEqual(value.members['b'].bufferRange.startPosition, 4)
        self.assertEqual(value.members['b'].bufferRange.size, 1)
        self.assertEqual(value.members['b'].decodedValue, 0xfe)

    def test_default_field_alignment(self):
        context = datatypes.InstantiateContext()
        context.fields = [
            datatypes.Structure.Field('a', self.typeManager.getTemplate('uint8')),
            datatypes.Structure.Field('b', self.typeManager.getTemplate('uint32'))
        ]
        value = self.typeManager.decode('struct', utils.DataCursor(b'\xfe\x00\x00\x00\xff\xff\xff\xff'), context)
        member_a = value.members['a']
        self.assertEqual((member_a.bufferRange.startPosition, member_a.bufferRange.size, member_a.decodedValue),
                         (0, 1, 0xfe))
        member_b = value.members['b']
        self.assertEqual((member_b.bufferRange.startPosition, member_b.bufferRange.size, member_b.decodedValue),
                         (4, 4, 0xffffffff))

    def test_forward_link_on_same_level(self):
        context = datatypes.InstantiateContext()
        context.fields = [
            datatypes.Structure.Field('a', self.typeManager.getTemplate('uint8'), align_hint=1),
            datatypes.Structure.Field('b', self.typeManager.getTemplate('fixed_string'), align_hint=1)
        ]
        context.links = [
            datatypes.Structure.Link('a', 'b.size')
        ]

        value = self.typeManager.decode('struct', utils.DataCursor(b'\x03hello'), context)
        member_a, member_b = value.members['a'], value.members['b']
        self.assertEqual((member_a.bufferRange.startPosition, member_a.bufferRange.size, member_a.decodedValue),
                         (0, 1, 3))
        self.assertEqual((member_b.bufferRange.startPosition, member_b.bufferRange.size, member_b.decodedValue),
                         (1, 3, 'hel'))

    def test_inner_link(self):
        a_context = datatypes.InstantiateContext()
        a_context.fields = [
            datatypes.Structure.Field('b', self.typeManager.getTemplate('uint8'), align_hint=1),
            datatypes.Structure.Field('c', self.typeManager.getTemplate('float'), align_hint=1)
        ]

        context = datatypes.InstantiateContext()
        context.fields = [
            datatypes.Structure.Field('a', self.typeManager.getTemplate('struct'), a_context, align_hint=1),
            datatypes.Structure.Field('d', self.typeManager.getTemplate('fixed_string'), align_hint=1)
        ]
        context.links = [
            datatypes.Structure.Link('a.b', 'd.size')
        ]

        value = self.typeManager.decode('struct', utils.DataCursor(b'\x04\xff\xff\xff\xffhello, world!'), context)
        self.assertEqual(value.members['d'].bufferRange.size, 4)
        self.assertEqual(value.members['d'].decodedValue, 'hell')

    def test_backdep_link_same_level(self):
        context = datatypes.InstantiateContext()
        context.fields = [
            datatypes.Structure.Field('dep_str', self.typeManager.getTemplate('fixed_string'), align_hint=1),
            datatypes.Structure.Field('encoding', self.typeManager.getTemplate('zero_string'), align_hint=1)
        ]
        context.fields[0].typeContext.size = 4
        context.links = [
            datatypes.Structure.Link('encoding', 'dep_str.encoding')
        ]

        d = b'o\x00k\x00utf-16le\x00'
        value = self.typeManager.decode('struct', utils.DataCursor(d), context)
        self.assertEqual(value.members['dep_str'].decodedValue, 'ok')

    def test_backdep_link_different_levels(self):
        a_context = datatypes.InstantiateContext()
        a_context.fields = [
            datatypes.Structure.Field('inner_fs', self.typeManager.getTemplate('fixed_string'), align_hint=1)
        ]
        a_context.fields[0].typeContext.size = 4

        b_context = datatypes.InstantiateContext()
        b_context.fields = [
            datatypes.Structure.Field('inner_size', self.typeManager.getTemplate('int8'), align_hint=1)
        ]

        context = datatypes.InstantiateContext()
        context.fields = [
            datatypes.Structure.Field('a', self.typeManager.getTemplate('struct'), a_context),
            datatypes.Structure.Field('b', self.typeManager.getTemplate('struct'), b_context)
        ]
        context.links = [
            datatypes.Structure.Link('b.inner_size', 'a.inner_fs.size')
        ]

        # structure decoder first decodes a.inner_fs with default size of 4 bytes and then decodes b.inner_size with
        # value of 10. It updates link and re-decodes a.inner_fs with new size of 10 bytes. Then it decodes b.inner_size
        # and gets its value which is equal to 10. This value already equal to a.inner_fs.size, so decoding continues.
        d = b'hell\x0aworld\x0a'
        value = self.typeManager.decode('struct', utils.DataCursor(d), context)
        mem_a = value.members['a'].members['inner_fs']
        mem_b = value.members['b'].members['inner_size']
        self.assertEqual((mem_a.bufferRange.startPosition, mem_a.bufferRange.size, mem_a.decodedValue),
                         (0, 10, 'hell\x0aworld'))
        self.assertEqual((mem_b.bufferRange.startPosition, mem_b.bufferRange.size, mem_b.decodedValue),
                         (10, 1, 10))


class StructureFieldTest(unittest.TestCase):
    class DummyTemplate(datatypes.AbstractTemplate):
        def __init__(self):
            super().__init__('dummy', adjustable_context_properties=dict(int=int, str=str))

    dummy_template = DummyTemplate()

    def test_has_prop(self):
        context = datatypes.InstantiateContext()
        field = datatypes.Structure.Field('some', self.dummy_template, context)
        self.assertTrue(field.hasProperty('int'))
        self.assertFalse(field.hasProperty('float'))
        self.assertFalse(field.hasProperty('another.int'))

        context.fields = [datatypes.Structure.Field('another', self.dummy_template, context)]
        self.assertTrue(field.hasProperty('another.int'))

    def test_set_prop(self):
        context = datatypes.InstantiateContext()
        field = datatypes.Structure.Field('some', self.dummy_template, context)
        field.setContextPropertyFromRawValue('int', 10)
        self.assertEqual(getattr(context, 'int'), 10)
        self.assertRaises(ValueError, lambda: field.setContextPropertyFromRawValue('int', '10'))

        context.fields = [datatypes.Structure.Field('another', self.dummy_template, context)]
        field.setContextPropertyFromRawValue('another.str', '10')
        self.assertEqual(getattr(context.fields[0].typeContext, 'str'), '10')
