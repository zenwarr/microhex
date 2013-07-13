from PyQt4.QtGui import QLineEdit, QValidator
import hex.formatters as formatters


class HexLineEdit(QLineEdit):
    def __init__(self, parent):
        QLineEdit.__init__(self, parent)
        self._validator = HexInputValidator()
        self.setValidator(self._validator)

    @property
    def data(self):
        formatter = formatters.IntegerFormatter(base=16)
        return b''.join(formatter.parse(i).to_bytes(1, byteorder='big') for i in self.text().split())


class HexInputValidator(QValidator):
    def validate(self, text, pos):
        # remove all spaces from text
        text = ''.join(text.split()).lower()

        if not text:
            return self.Intermediate, '', 0

        # check if text contains only hex digits
        for char in text:
            if char not in '1234567890abcedef':
                return self.Invalid, self._format(text), pos + pos // 2

        return self.Acceptable, self._format(text), pos + pos // 2

    def _format(self, text):
        return ''.join(text[i:i+2] + ' ' for i in range(0, len(text), 2)).strip()
