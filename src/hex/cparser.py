import random
import re
import tempfile
import hex.datatypes as datatypes
import hex.utils as utils
import hex.settings as settings
import hex.appsettings as appsettings

has_pycparser = False
try:
    import pycparser
    import ply.lex as lex
    has_pycparser = True
except ImportError:
    print('pycparser module should be installed to parse C headers')


class ParseError(Exception):
    pass


class CParser:
    class ParseContext:
        def __init__(self):
            self.templates = dict()

    def __init__(self, type_manager=None, namespaces=None):
        self.cppPath = 'cpp'  # path to C preprocessor
        self.cppArgs = ''  # additional arguments to C preprocessor
        self.tabWidth = 4  # tab width is required to correct indents in embedded Python code
        self.typeManager = type_manager or datatypes.globalTypeManager()  # used as source of templates
        self.namespaces = namespaces or ['platform']  # additional namespaces where parser will search for templates

    def parseText(self, text, d_filename=''):
        """Returns dictionary where key is template name and value is context for this type.
        d_filename will be used in error messages.
        """
        self._ensureConfigured()

        parse_context = self.ParseContext()

        # we should extract meta-information from code before clearing it from preprocessor directives and comments
        self._extractMeta(parse_context, text)

        # now feed preprocessor. Create temp file and write our code into it.
        with tempfile.NamedTemporaryFile('w+t') as temp_file:
            # to enable use of already known types in header, we should generate C definitions for them and include
            # before header code. We should skip them in generated AST.
            temp_file.write(self._generateTypedefsCode(parse_context) + '\n\n')
            temp_file.write(text)
            temp_file.flush()

            try:
                ast = pycparser.parse_file(temp_file.name, use_cpp=True, cpp_path=self.cppPath, cpp_args=self.cppArgs)
            except pycparser.plyparser.ParseError as err:
                raise ParseError(str(err))

        # now process AST
        for ext in ast.ext:
            if isinstance(ext, pycparser.c_ast.Decl):
                if isinstance(ext.type, pycparser.c_ast.Struct):
                    # something like 'struct A { int x; }'
                    self._processStruct(parse_context, ext.type)
                elif isinstance(ext.type, pycparser.c_ast.TypeDecl) and isinstance(ext.type.type, pycparser.c_ast.Struct):
                    # something like 'struct A { int x; } my_var;'
                    self._processStruct(parse_context, ext.type.type)
            elif isinstance(ext, pycparser.c_ast.Typedef):
                self._processTypedef(parse_context, ext)

        return parse_context

    def parseFile(self, filename):
        with open(filename, 'r+t') as f:
            return self.parseText(f.read(), filename)

    def getTemplateChecked(self, templ_name):
        templ = self.getTemplate(templ_name)
        if templ is None:
            raise ParseError('template {0} not found'.format(templ_name))
        return templ

    def getTemplate(self, templ_name):
        if isinstance(templ_name, (tuple, list)):
            for name in templ_name:
                templ = self.getTemplate(name)
                if templ is not None:
                    return templ
            else:
                return None

        templ = self.typeManager.getTemplate(templ_name)
        if templ is None:
            if templ_name.startswith('.'):
                templ_name = templ_name[1:]
            for ns_name in self.namespaces:
                templ = self.typeManager.getTemplate(ns_name + '.' + templ_name)
                if templ is not None:
                    break
        return templ

    # private

    def _getTemplateWithContextChecked(self, parse_context, templ_name):
        template = self.getTemplate(templ_name)
        if template is None:
            template = parse_context.templates.get(templ_name)
            if template is None:
                raise ParseError(utils.tr('structure {0} not found').format(templ_name))
        return template

    def _processStruct(self, parse_context, struct) -> str:
        """Returns name for created template.
        """
        if struct.decls is None:
            # something like 'struct SOME_STRUCT a;' - just a definition of variable
            return

        struct_name = None
        if struct.name is None:
            # anonimuos structure... create meaningless name for it
            while True:
                struct_name = '__anon_struct_' + str(random.randint(1, 100000))
                if struct_name not in parse_context.templates:
                    break
        else:
            if struct.name in parse_context.templates:
                # prevent from overriding template with another one
                raise ParseError(utils.tr('overriding name {0} at {1}:{2}').format(struct.name, struct.coord.file,
                                                                                   struct.coord.line))
            struct_name = struct.name

        context_builder = datatypes.StructureContextBuilder()
        for decl in struct.decls:
            name = decl.name
            if isinstance(decl.type.type, pycparser.c_ast.IdentifierType):
                template = self.getTemplateChecked(decl.type.type.names[0])
            elif isinstance(decl.type.type, pycparser.c_ast.Struct):
                field_struct = decl.type.type
                if field_struct.decls is not None:
                    # struct A { struct B { int b_m; } a_m; };
                    # create template for this structure and create field with given name. In case of inner structure
                    # declaration (struct A { struct B { int b_m; }; };) B will become member of same namespace
                    # that contains A.
                    self._processStruct(parse_context, field_struct)
                    assert(field_struct.name in parse_context.templates)
                    template = parse_context.templates[field_struct.name]
                else:
                    # try to find structure template with given name in type manager or in parse context
                    template = self._getTemplateWithContextChecked(parse_context, field_struct.name)
            else:
                raise ParseError('what the fuck?')
            context_builder.addField(name, template)

        template = datatypes.Structure()
        template.realName = struct_name
        template.defaultsContext = context_builder.context
        parse_context.templates[struct_name] = template
        return struct_name

    def _processTypedef(self, parse_context, typedef):
        assert(isinstance(typedef.type, pycparser.c_ast.TypeDecl))
        original_type = typedef.type.type
        if isinstance(original_type, pycparser.c_ast.Struct):
            if original_type.decls is not None:
                # typedef struct { ... } STRUCT_NAME;
                template_name = self._processStruct(parse_context, original_type)
                template = parse_context.templates[template_name]
                if template.realName.startswith('__'):
                    template.realName = typedef.name
                    del parse_context.templates[template_name]
                    parse_context.templates[typedef.name] = template
            else:
                # typedef struct SOME_STRUCT STRUCT_ALIAS;
                assert(original_type.name is not None)
                template = self._getTemplateWithContextChecked(parse_context, original_type.name)
                parse_context.templates[typedef.name] = template.clone()
        elif isinstance(original_type, pycparser.c_ast.IdentifierType):
            template = self._getTemplateWithContextChecked(parse_context, original_type.names[0])
            parse_context.templates[typedef.name] = template.clone()

    def _extractMeta(self, parse_context, code):
        """File can contain meta-information in comments. Each comment that contains meta information should start
        with : char.
            //: <meta-information>
            /*: <meta-information>
            **  <meta-information>
            */
        Meta properties:
            property = ident, "=", value
            ident = letter | "_", { letter | digit | "_" }
            value = string-literal | number-literal | code-literal
            string-literal = ('"', any character except \", "'") | ("'", any character except \', "'") | ident
            number-literal = ("0x", { hex_digit} ) | ("0b", { bin_digit } ) | {dec_digit}
            code-literal = ">>>", any python code, "<<<"
            list-literal = "[", value, "]"

            code-literal and list-literal can span on multiple lines. In this case, each line should be commented.
            For example:
                int a; //: list = [value1,
                       //:         value2,
                       //:         value3]

            and multiline one:
                int a; /*: list = [value1,
                        *          value2,
                        *          value3]
                        */

            You cannot place C comments inside meta-information comments.

            In code-literal start of each line is considered to be at position of first code character of first line of
            code-literal. For example, following meta-info contains valid (in meaning of whitespaces) Python code:

            /*: my_code = >>>def func(a, b):
             *                   return a + b
             */

        Example:
            int a; //: name=some_name, text="some text", text2='some text', transform=>>>value.trim()<<<

        Allowed meta-information:
            Global scope: placed in top of file, before any declaration.
                requires = list-literal | string-literal
                Determines which type manager namespaces can be used. After specifying that namespace is required,
                you can use templates from this namespace (without any name decorations).

                mhversion = string-literal
                Minimal required Microhex version that can load this file.

                platform = string-literal
                Determines which platform should be used by type manager. In fact, this directive results in
                including additional namespace containing platform definitions in 'requires' with difference that
                you cannot know name of this namespaces.

            Top definition scope:
                pass

            Definition scope:
                pass

        This method adds 'metas' attribute to parse context. 'metas' is
        """

        tab_width = settings.globalSettings()[appsettings.CParser_TabWidth]
        lines = code.split('\n')  # does it work both for CR and CR-LF?
        line_index = 0
        while line_index < len(lines):
            line = lines[line_index]

            char_index = 0
            current_width = 0

            def inc_char(char):
                nonlocal char_index
                nonlocal current_width
                char_index += 1
                current_width += 1 if char != '\t' else tab_width

            while char_index < len(line):
                char = line[char_index]
                if char == '"':
                    # ignore strings because ones can contain // or /*
                    while char_index < len(line):
                        if char == '\\':
                            # escaping: ignore next character and continue
                            inc_char(char)
                        elif char == '"':
                            # end of string literal
                            inc_char(char)
                            break
                        inc_char(char)
                        char = line[char_index]
                elif char == '/':
                    marker_cand = line[char_index:char_index+3]
                    meta_lines = list()
                    if marker_cand == '//:':
                        # enter meta-info with single-line comment
                        meta_lines.append((char_index + 3, line[char_index+3:]))
                        line_index += 1
                        while line_index < len(lines):
                            line = lines[line_index].strip()
                            if line:
                                if not line.startswith('//:'):
                                    # back to previous line: there is a code
                                    line_index -= 1
                                    break
                                else:
                                    # continuation of spanned single-line comment
                                    meta_start = lines[line_index].index('\\:') + 3
                                    meta_lines.append((meta_start, line[meta_start:]))
                    #elif marker_cand == '/*:':
                    #    # enter meta-info with multi-line comment
                    #    # we should scan line until comment close marker is met. There can be two or more meta-comments
                    #    # in one line. Consecutive code lines should be scanned too.

                    if meta_lines:
                        self._processMetaLines(parse_context, meta_lines, line_index)

                inc_char(char)

            line_index += 1

    def _processMetaLines(self, parse_context, meta_lines, first_line_index):
        # meta_lines is list of tuples (start_offset, text)
        # make text from these lines
        meta_text = '\n'.join(d[1] for d in meta_lines)

        lex = self.MetaLexer()
        lex.build()
        lex.lexer.input(meta_text)

        result = {}
        while True:
            tok = lex.lexer.token()
            if tok is None:
                break
            if tok.type == 'IDENT':
                key = tok.value

                tok = lex.lexer.token()
                if tok is None or tok.type != 'EQUAL':
                    raise ParseError('= expected after {0}'.format(key))

                tok = lex.lexer.token()
                if tok.type in ('IDENT', 'STRING_LITERAL', 'BINARY_LITERAL', 'HEX_LITERAL', 'DECIMAL_LITERAL'):
                    value = tok.value
                elif tok.type == 'CODE_LITERAL':
                    # now adjust spaces in code. We should remove some leading whitespaces on each line. We should also
                    # remove first line if it is empty
                    tok.value = tok.value.replace('\t', ' ' * settings.globalSettings()[appsettings.CParser_TabWidth])

                    code_lines = tok.value.split('\n')
                    if len(code_lines) > 1:
                        # get first line and determine space character count before actual code start
                        align_space_count = meta_lines[tok.lineno][0] + (len(code_lines[0]) - len(code_lines[0].lstrip()))
                        for code_line, code_line_index in zip(code_lines[1:], itertools.count()):
                            leading_space_count = (len(code_line) - len(code_line.lstrip()))
                            space_count = meta_lines[tok.lineno][0] + leading_space_count
                            if space_count < align_space_count:
                                raise ParseError('bad code indentation near {0}'.format(code_line))
                            code_line[code_line_index] = ' ' * (space_count - align_space_count) + code_line.lstrip()
                    else:
                        code_lines[0] = tok.value.lstrip()

                    value = self._CodeEvaluator('\n'.join(code_lines))
                else:
                    raise ParseError('value expected after =')

                result[key] = value

                tok = lex.lexer.token()
                if tok is None:
                    break
                elif tok.type != 'COMMA':
                    raise ParseError(', expected after property {0}'.format(key))

        return result

    class MetaLexer:
        tokens = ('IDENT', 'STRING_LITERAL', 'BINARY_LITERAL', 'HEX_LITERAL', 'DECIMAL_LITERAL', 'CODE_LITERAL',
                  'COMMA', 'EQUAL')

        t_IDENT = '[a-zA-Z_][a-zA-Z_0-9]*'
        t_COMMA = ','
        t_EQUAL = '='

        def t_STRING_LITERAL(self, t):
            r'("(\\.|[^\"\n])*")|(\'(\\.|[^\\\'\n])*\')'  # fucking magic
            t.value = t.value[1:-1]
            return t

        def t_BINARY_LITERAL(self, t):
            '0[bB][01]+'
            t.value = int(t.value[2:], base=2)
            return t

        def t_HEX_LITERAL(self, t):
            '0[xX][0-9a-fA-F]+'
            t.value = int(t.value[2:], base=16)
            return t

        def t_DECIMAL_LITERAL(self, t):
            r'[0-9]+'
            t.value = int(t.value)
            return t

        def t_CODE_LITERAL(self, t):
            '(?i)>>>.*<<<'
            t.value = t.value[3:-3]
            return t

        def t_error(self, t):
            print('lexer error "{0}"'.format(t.value[0]))
            t.lexer.skip(1)

        t_ignore = ' \t'

        def build(self, **kwargs):
            if not has_pycparser:
                raise ParseError('pycparser is not installed')
            self.lexer = lex.lex(module=self, reflags=re.DOTALL, **kwargs)

    class _CodeEvaluator:
        def __init__(self, code):
            self.code = code

    def _ensureConfigured(self):
        if not has_pycparser:
            raise ParseError('pycparser is not installed')
        elif not self.cppPath:
            raise ParseError('cpp should be configured to parse headers, adjust cparser.cpp_path setting variable')

    def _generateTypedefsCode(self, parse_context):
        pass


globalCParser = utils.createSingleton(CParser)
for attr_name, setting_name in dict(cppPath='cpp_path', cppArgs='cpp_args', tabWidth='tab_width').items():
    setattr(globalCParser(), attr_name, settings.globalSettings().get(getattr(appsettings, 'cparser' + setting_name)))
