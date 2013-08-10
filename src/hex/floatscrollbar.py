from PyQt4.QtGui import QScrollBar
from PyQt4.QtCore import pyqtSignal, Qt


class LargeScrollBar(QScrollBar):
    rangeChangedLarge = pyqtSignal(int, int)
    sliderMovedLarge = pyqtSignal(int)
    valueChangedLarge = pyqtSignal(int)

    def __init__(self, orientation=Qt.Vertical, parent=None):
        QScrollBar.__init__(self, orientation, parent)
        self._min = 0
        self._max = 100
        self._pageStep = 10
        self._singleStep = 1
        self._ticks = 1000000
        self._exactValue = 0
        self._valueRange = (0, 0)

        self.valueChanged.connect(self._onValueChanged)
        self.sliderMoved.connect(self._onSliderMoved)

        self.setRange(0, self._ticks)

    def maximumLarge(self):
        return self._max

    def minimumLarge(self):
        return self._min

    def pageStepLarge(self):
        return self._pageStep

    def singleStepLarge(self):
        return self._singleStep

    def valueLarge(self):
        return self._exactValue

    def setMaximumLarge(self, new_max):
        self.setRangeLarge(self.minimumLarge(), new_max)

    def setMinimumLarge(self, new_min):
        self.setRangeLarge(new_min, self.maximumLarge())

    def setPageStepLarge(self, new_page_step):
        if self._pageStep != new_page_step:
            self._pageStep = new_page_step
            self.setPageStep(int(self._ticksToValue(self._pageStep)))

    def setValueLarge(self, new_value):
        if not (self._valueRange[0] <= new_value < self._valueRange[1]):
            self._exactValue = new_value

            ticks = self._valueToTicks(new_value)
            self._valueRange = (int(self._ticksToValue(ticks)), int(self._ticksToValue(ticks + 1)))
            self.setValue(ticks)

    def setRangeLarge(self, new_min, new_max):
        self._min = min(new_min, new_max)
        self._max = max(new_min, new_max)

        if self._max - self._min < self._ticks:
            self.setRange(0, int(self._max - self._min))
        else:
            self.setRange(0, self._ticks)

        self.rangeChangedLarge.emit(self.minimumLarge(), self.maximumLarge())

    def _valueToTicks(self, value):
        if self._max - self._min < self._ticks:
            return int(value)
        return int(value / (self._max - self._min) * self._ticks)

    def _ticksToValue(self, ticks):
        if self._max - self._min < self._ticks:
            return ticks
        return self._min + ticks / self._ticks * (self._max - self._min)

    def _onValueChanged(self, ticks):
        value = round(self._ticksToValue(ticks))
        if not (self._valueRange[0] <= value <= self._valueRange[1]):
            self.setValueLarge(value)
            self.valueChangedLarge.emit(value)

    def _onSliderMoved(self, ticks):
        value = round(self._ticksToValue(ticks))
        if not (self._valueRange[0] <= value <= self._valueRange[1]):
            self.sliderMovedLarge.emit(self._valueToTicks(value))
