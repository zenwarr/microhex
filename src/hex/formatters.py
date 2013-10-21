from PyQt4.QtGui import QValidator


class IntegerFormatter(object):
    StyleNone, StyleC, StyleAsm = range(3)

    def __init__(self, base=10, style=StyleNone, padding=0, uppercase=False):
        self.base = base
        self._style = self.StyleNone
        self.style = style
        self.padding = padding
        self.uppercase = uppercase

    @property
    def style(self):
        return self._style

    @style.setter
    def style(self, new_style):
        if new_style != self._style:
            if isinstance(new_style, str):
                self._style = self.styleFromName(new_style)
            else:
                self._style = new_style

    @property
    def styleName(self):
        if self.style == self.StyleNone:
            return 'none'
        elif self.style == self.StyleC:
            return 'c'
        elif self.style == self.StyleAsm:
            return 'asm'

    def format(self, value):
        result = ''

        if value != 0:
            current = abs(value)
            while current != 0:
                remainder = current % self.base
                if remainder < 10:
                    result += str(remainder)
                else:
                    result += chr(ord('A' if self.uppercase else 'a') + remainder - 10)
                current = (current - remainder) // self.base

            result = result[::-1]
        else:
            result = '0'

        if self.padding > 0 and self.padding - self._decorationLength() - len(result) > 0:
            result = result.zfill(self.padding - self._decorationLength())

        if value < 0:
            result = '-' + result

        result = self._decorate(result)

        return result

    def parse(self, value):
        value = self._undecorate(value)
        return int(value, self.base)

    def _decorationLength(self):
        if self.style == self.StyleC:
            if self.base in (2, 8, 16):
                return 2
        elif self.style == self.StyleAsm:
            if self.base in (2, 8, 16):
                return 1
        return 0

    def _decorate(self, value):
        if self.style == self.StyleC:
            if self.base == 16:
                return '0x' + value
            elif self.base == 8:
                return '0o' + value
            elif self.base == 2:
                return '0b' + value
        elif self.style == self.StyleAsm:
            if self.base == 16:
                return value + 'h'
            elif self.base == 8:
                return value + 'o'
            elif self.base == 2:
                return value + 'b'
        return value

    def _undecorate(self, value):
        value = value.lower()
        if self.style == self.StyleC:
            if self.base == 16:
                if value.startswith('0x'):
                    return value[2:]
            elif self.base == 8:
                if value.startswith('0o'):
                    return value[2:]
            elif self.base == 2:
                if value.startswith('0b'):
                    return value[2:]
        elif self.style == self.StyleAsm:
            if self.base in (16, 8, 2):
                return value[:-1]
        return value

    @staticmethod
    def guessFormat(text):
        """Returns tuple (style, base) or None when format is not guessed. Method does not detects plain integers
        and C-style octals."""
        text = text.lower()
        if text.startswith('0x'):
            return (IntegerFormatter.StyleC, 16)
        elif text.startswith('0b'):
            return (IntegerFormatter.StyleC, 2)
        elif text.startswith('0o'):
            return (IntegerFormatter.StyleC, 8)
        elif text.endswith('h'):
            return (IntegerFormatter.StyleAsm, 16)
        elif text.endswith('o'):
            return (IntegerFormatter.StyleAsm, 8)
        elif text.endswith('b'):
            return (IntegerFormatter.StyleAsm, 2)
        return None

    def validate(self, text):
        if not text or text == '-':
            return QValidator.Intermediate
        try:
            undecorated = self._undecorate(text)
            if not undecorated:
                return QValidator.Intermediate
            elif undecorated != undecorated.strip():
                return QValidator.Invalid
            self.parse(text)
            return QValidator.Acceptable
        except ValueError:
            return QValidator.Invalid

    @staticmethod
    def styleFromName(name):
        name = name.lower()
        if name == 'c':
            return IntegerFormatter.StyleC
        elif name in ('asm', 'assembler'):
            return IntegerFormatter.StyleAsm
        return IntegerFormatter.StyleNone


def parseInteger(text):
    guessed = IntegerFormatter.guessFormat(text)
    if guessed is None:
        return IntegerFormatter().parse(text)
    else:
        return IntegerFormatter(guessed[1], guessed[0]).parse(text)


class FloatFormatter(object):
    def __init__(self, precision=12):
        self.precision = precision
        self.align = True

    def format(self, value):
        format_spec = '{0:#' + (str(self.maximalWidth) if self.align else '0') + '.' + str(self.precision) + 'e}'
        return format_spec.format(value)

    def parse(self, value):
        if value.strip() != value:
            return QValidator.Invalid
        return float(value)

    @property
    def maximalWidth(self):
        return 3 + self.precision + 2 + 3
