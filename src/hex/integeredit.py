from PyQt4.QtCore import QMargins, pyqtSignal, Qt
from PyQt4.QtGui import QAbstractSpinBox, QToolButton, QMenu, QActionGroup, QValidator
import hex.utils as utils
import hex.settings as settings
import hex.appsettings as appsettings
import hex.formatters as formatters


globalSettings = settings.globalSettings()


class IntegerEdit(QAbstractSpinBox):
    numberChanged = pyqtSignal(int)

    def __init__(self, parent, base=16, minimum=0, maximum=-1):
        QAbstractSpinBox.__init__(self, parent)
        self._min = minimum
        self._max = maximum
        self.step = 1
        self._number = 0

        self._baseButton = QToolButton(self)
        self._baseButton.setStyleSheet('QToolButton::menu-indicator { image: none; }')
        self._baseButton.setFocusPolicy(Qt.NoFocus)
        self._baseMenu = QMenu()
        self._baseActionGroup = QActionGroup(self)
        self._baseActionGroup.setExclusive(True)
        self._baseButton.setMenu(self._baseMenu)
        self._baseButton.setPopupMode(QToolButton.InstantPopup)
        self._baseButton.setText(str(base))

        style = globalSettings[appsettings.IntegerEdit_DefaultStyle]
        self._formatter = formatters.IntegerFormatter(base, style, uppercase=globalSettings[appsettings.IntegerEdit_Uppercase])

        for standard_base in (('Hex', 16), ('Dec', 10), ('Oct', 8), ('Bin', 2)):
            self._addBase(utils.tr(standard_base[0]), standard_base[1])

        self._defaultLeftMargin = self.lineEdit().getTextMargins()[0]
        self._updateBaseButton()

        self.number = self._min
        self.lineEdit().setCursorPosition(0)

        self.lineEdit().textChanged.connect(self._onTextChanged)

    def minimumSizeHint(self):
        min_size = QAbstractSpinBox.minimumSizeHint(self)
        min_button_size = self._baseButton.minimumSizeHint()
        min_size.setHeight(max(min_size.height(), min_button_size.height() + 4))
        min_size.setWidth(min_size.width() + min_button_size.width() + 4)
        return min_size

    def resizeEvent(self, event):
        QAbstractSpinBox.resizeEvent(self, event)
        self._updateBaseButton()

    def _addBase(self, name, base):
        action = self._baseMenu.addAction(name)
        action.setData(base)
        action.setCheckable(True)
        action.triggered.connect(self._setBaseFromAction)
        self._baseActionGroup.addAction(action)
        if base == self.base:
            action.setChecked(True)

    def _updateBaseButton(self):
        button_size = self.size().height() - 2 * 2
        self._baseButton.setGeometry(2, 2, button_size, button_size)

        margins = self.lineEdit().getTextMargins()
        self.lineEdit().setTextMargins(QMargins(max(self._defaultLeftMargin, button_size + 2 * 2), margins[1],
                                                margins[2], margins[3]))

    @property
    def base(self):
        return self._formatter.base

    @base.setter
    def base(self, base):
        self._setBase(base)

    def _setBase(self, base, convert_number=True):
        """If :convert_number: is True, text in widget will be converted to new base. Otherwise text will
        be assumed to be in base we are converting to.
        """
        if base != self._formatter.base:
            # we should not try to convert empty string into another base, but if string is Invalid or Intermediate
            # it would be converted to empty string.
            new_text = self.lineEdit().text()
            if self._formatter.validate(self.lineEdit().text()) != QValidator.Acceptable:
                new_text = ''
                number = 0
            else:
                number = self._formatter.parse(new_text)

            for action in self._baseActionGroup.actions():
                if action.data() == base:
                    action.setChecked(True)
                    break
            else:
                self._baseActionGroup.checkedAction().setChecked(False)

            self._formatter.base = base
            self._baseButton.setText(str(base))

            # should be convert this this text to new base?
            if convert_number and new_text:
                self.lineEdit().setText(self._formatter.format(number))
            else:
                self.lineEdit().setText(new_text)

    def _setBaseFromAction(self):
        self.base = self.sender().data()

    @property
    def number(self):
        if self._formatter.validate(self.lineEdit().text()) == QValidator.Acceptable:
            return self._formatter.parse(self.lineEdit().text())
        return 0

    @number.setter
    def number(self, new_number):
        if self.number != new_number or self._doValidate(self.text(), 0, False) != QValidator.Acceptable:
            self.lineEdit().setText(self._formatter.format(new_number))

    @property
    def minimum(self):
        return self._min

    @property
    def maximum(self):
        return self._max

    @minimum.setter
    def minimum(self, n_min):
        if self._max >= 0:
            self._min = min(n_min, self._max)
        else:
            self._min = n_min
        if self.number < n_min:
            self.number = n_min

    @maximum.setter
    def maximum(self, n_max):
        self._max = max(n_max, self._min)
        if self._max >= 0 and self._number > self._max:
            self.number = self._max

    def stepBy(self, steps):
        n_num = self.number + steps * self.step
        if n_num < self._min:
            n_num = self._min
        elif self._max >= 0 and n_num > self._max:
            n_num = self._max
        self.number = n_num

    def stepEnabled(self):
        return self.StepEnabled((self.StepUpEnabled if self._max < 0 or self.number < self._max else 0) |
                        (self.StepDownEnabled if self.number > self._min else 0))

    def _onTextChanged(self, new_text):
        if (self._doValidate(new_text, self.lineEdit().cursorPosition(), False) == QValidator.Acceptable
                    and self._number != self.number):
            self._number = self.number
            self.numberChanged.emit(self.number)

    def _doValidate(self, text, pos, correct):
        status = self._formatter.validate(text)
        if status == QValidator.Invalid:
            # try to guess base and style in which number is typed.
            if correct:
                guessed = formatters.IntegerFormatter.guessFormat(text)
                if guessed is not None:
                    if guessed[0] != self._formatter.style:
                        self._formatter.style = guessed[0]
                    if guessed[1] != self._formatter.base:
                        self._setBase(guessed[1], False)
                    status = self._formatter.validate(text)

        if status == QValidator.Acceptable:
            # check if number is in allowed range.
            num = self._formatter.parse(text)
            if num < self._min or (self._max >= 0 and num > self._max):
                status = QValidator.Invalid
        elif status == QValidator.Intermediate and text.startswith('-'):
            # check if user has typed minus sign and minimal value is not negative
            if self._min >= 0:
                status = QValidator.Invalid
        return status

    def validate(self, text, pos):
        return self._doValidate(text, pos, True), text, pos

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            # helpful shortcut for quick access to min and max values...
            if event.key() == Qt.Key_Up:
                if self._max >= 0:
                    self.number = self._max
                return
            elif event.key() == Qt.Key_Down:
                self.number = self._min
                return
        QAbstractSpinBox.keyPressEvent(self, event)
