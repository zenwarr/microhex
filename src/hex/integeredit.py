from PyQt4.QtCore import QSize, QMargins, pyqtSignal, Qt
from PyQt4.QtGui import QAbstractSpinBox, QToolButton, QMenu, QActionGroup, QValidator
import hex.utils as utils
import hex.settings as settings
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
        # self._baseButton.setAutoRaise(True)
        self._baseButton.setStyleSheet('QToolButton::menu-indicator { image: none; }')
        self._baseButton.setFocusProxy(self.lineEdit())
        self._baseMenu = QMenu()
        self._baseActionGroup = QActionGroup(self)
        self._baseActionGroup.setExclusive(True)
        self._baseButton.setMenu(self._baseMenu)
        self._baseButton.setPopupMode(QToolButton.InstantPopup)
        self._baseButton.setText(str(base))

        style = globalSettings['integeredit.default_style']
        self._formatter = formatters.IntegerFormatter(base, style, uppercase=globalSettings['integeredit.uppercase'])

        for standard_base in (('Hex', 16), ('Dec', 10), ('Oct', 8), ('Bin', 2)):
            self._addBase(utils.tr(standard_base[0]), standard_base[1])

        self._defaultLeftMargin = self.lineEdit().getTextMargins()[0]

        min_size = self.minimumSize()
        min_size.setWidth(min_size.width() + self._baseButton.minimumSize().width() + 4)
        min_size.setHeight(max(min_size.height(), self._baseButton.minimumSize().height() + 4))
        self.setMinimumSize(min_size)

        self._updateBaseButton()
        self.number = self._min
        self.lineEdit().setCursorPosition(0)

        self.lineEdit().textChanged.connect(self._onTextChanged)

    def minimumSizeHint(self):
        min_size = QAbstractSpinBox.minimumSizeHint(self)
        min_button_size = self._baseButton.minimumSizeHint()
        min_size.setHeight(max(min_size.height(), min_button_size.height()))
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
        self.lineEdit().setTextMargins(QMargins(self._defaultLeftMargin + button_size + 2 * 2, margins[1],
                                                margins[2], margins[3]))

    @property
    def base(self):
        return self._formatter.base

    @base.setter
    def base(self, base):
        self._setBase(base)

    def _setBase(self, base, convert_number=True):
        if base != self._formatter.base:
            if convert_number and self.text():
                number = self.number

            for action in self._baseActionGroup.actions():
                if action.data() == base:
                    action.setChecked(True)
                    break
            else:
                self._baseActionGroup.checkedAction().setChecked(False)

            self._formatter.base = base
            self._baseButton.setText(str(base))

            # convert number we have into different base
            if convert_number and self.text():
                self.number = number

    def _setBaseFromAction(self):
        self.base = self.sender().data()

    @property
    def number(self):
        if self.validate(self.text(), 0)[0] == QValidator.Acceptable:
            return self._formatter.parse(self.lineEdit().text())
        return 0

    @number.setter
    def number(self, new_number):
        if self.number != new_number or self.validate(self.text(), 0) != QValidator.Acceptable:
            self.lineEdit().setText(self._formatter.format(new_number))

    def validate(self, text, pos):
        r = self._formatter.validate(text)
        if r == QValidator.Invalid:
            guessed = formatters.IntegerFormatter.guessFormat(text)
            if guessed is not None:
                if guessed[0] != self._formatter.style:
                    self._formatter.style = guessed[0]
                if guessed[1] != self._formatter.base:
                    self._setBase(guessed[1], False)
                r = self._formatter.validate(text)

        if r == QValidator.Acceptable:
            num = self._formatter.parse(text)
            if num < self._min or (self._max >= 0 and num > self._max):
                r = QValidator.Invalid
        elif r == QValidator.Intermediate and text == '-':
            if self._min >= 0:
                r = QValidator.Invalid

        return r, text, pos

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
        if self._max >= 0 and self.number > self._max:
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
        if self._number != self.number:
            self.number = self.number
            self.numberChanged.emit(self.number)

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
