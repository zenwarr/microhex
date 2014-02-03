import hex.cparser as cparser
import unittest
import hex.datatypes as datatypes
import hex.utils as utils


def has_field(context, field_name):
    return utils.first(field for field in context.fields if field.name == field_name) is not None


class TestCParser(unittest.TestCase):
    prs = cparser.CParser()
    prs.useCpp = False

    def testSimpleStructure(self):
        code = 'struct A { int memb_a, memb_b; char memb_c; };'
        parse_context = self.prs.parseText(code)
        self.assertEqual(len(parse_context.templates), 1)
        A_context = parse_context.templates['A'].defaultsContext
        self.assertEqual(len(A_context.fields), 3)

        self.assertTrue(has_field(A_context, 'memb_a'))
        self.assertTrue(has_field(A_context, 'memb_b'))
        self.assertTrue(has_field(A_context, 'memb_c'))

    def test_nested_structures_with_def(self):
        code = 'struct A { struct B { int a; } b; };'
        parse_context = self.prs.parseText(code)
        self.assertIn('A', parse_context.templates)
        self.assertIn('B', parse_context.templates)
        self.assertTrue(has_field(parse_context.templates['A'].defaultsContext, 'b'))
        self.assertFalse(has_field(parse_context.templates['A'].defaultsContext, 'a'))
        self.assertTrue(has_field(parse_context.templates['B'].defaultsContext, 'a'))

        b_field = utils.first(field for field in parse_context.templates['A'].defaultsContext.fields if field.name == 'b')
        self.assertIs(b_field.template, parse_context.templates['B'])

    def test_reference_to_structure(self):
        code = 'struct B { int x; }; struct A { struct B b; };'
        parse_context = self.prs.parseText(code)
        self.assertIn('A', parse_context.templates)
        self.assertIn('B', parse_context.templates)
        self.assertTrue(has_field(parse_context.templates['A'].defaultsContext, 'b'))
        self.assertFalse(has_field(parse_context.templates['A'].defaultsContext, 'x'))
        self.assertTrue(has_field(parse_context.templates['B'].defaultsContext, 'x'))

        b_field = utils.first(field for field in parse_context.templates['A'].defaultsContext.fields if field.name == 'b')
        self.assertIs(b_field.template, parse_context.templates['B'])

    def test_unknown_structure_raises(self):
        code = 'struct A { struct B b; };'
        self.assertRaises(cparser.ParseError, lambda: self.prs.parseText(code))

    def test_typedef_decl(self):
        code = 'typedef struct { int a, b; } SOME_STRUCT, SOME_ALIAS;'
        parse_context = self.prs.parseText(code)

        self.assertIn('SOME_STRUCT', parse_context.templates)
        self.assertIn('SOME_ALIAS', parse_context.templates)

    def test_typedef_decl_diff(self):
        code = 'struct A { int a, b; }; typedef struct A SOME_STRUCT, SOME_ALIAS;'
        parse_context = self.prs.parseText(code)

        self.assertIn('SOME_STRUCT', parse_context.templates)
        self.assertIn('SOME_ALIAS', parse_context.templates)
        self.assertIn('A', parse_context.templates)

    def test_primitive_type_typedef(self):
        parse_context = self.prs.parseText('typedef int INT_ALIAS;')
        self.assertIn('INT_ALIAS', parse_context.templates)
        self.assertNotIn('int', parse_context.templates)
        self.assertTrue(isinstance(parse_context.templates['INT_ALIAS'], datatypes.AbstractIntegerTemplate))


class TestMetaLexer(unittest.TestCase):
    def test_tokens(self):
        lex = cparser.CParser.MetaLexer()
        lex.build()
        lex.lexer.input("09120 name='value', another=value, number=0x120, number=0b101010, yanum=1092, "
                        "code=>>>print('hello!')<<<")
        tokens = []
        while True:
            tok = lex.lexer.token()
            if tok is None:
                break
            tokens.append(tok)

        for d in zip(tokens, (('DECIMAL_LITERAL', 9120), ('IDENT', 'name'), ('EQUAL', '='), ('STRING_LITERAL', 'value'),
                              ('COMMA', ','), ('IDENT', 'another'), ('EQUAL', '='), ('IDENT', 'value'),
                              ('COMMA', ','), ('IDENT', 'number'), ('EQUAL', '='), ('HEX_LITERAL', 0x120),
                              ('COMMA', ','), ('IDENT', 'number'), ('EQUAL', '='), ('BINARY_LITERAL', 0b101010),
                              ('COMMA', ','), ('IDENT', 'yanum'), ('EQUAL', '='), ('DECIMAL_LITERAL', 1092),
                              ('COMMA', ','), ('IDENT', 'code'), ('EQUAL', '='), ('CODE_LITERAL', "print('hello!')"))):
            self.assertEqual(d[0].type, d[1][0])
            self.assertEqual(d[0].value, d[1][1])

