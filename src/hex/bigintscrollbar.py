from PyQt4.QtGui import QWidget, QScrollBar, QHBoxLayout
from PyQt4.QtCore import pyqtSignal, Qt
import math


MaximumTickCount = 0x7fffffff


class BigIntScrollBar(QWidget):
    rangeChanged = pyqtSignal(object, object)
    valueChanged = pyqtSignal(object)

    def __init__(self, orientation, parent):
        QWidget.__init__(self, parent)

        self._sbar = QScrollBar(orientation, self)
        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self._sbar)

        self._min = 0
        self._max = 100
        self._pageStep = 10
        self._singleStep = 1
        self._exactValue = 0
        self._currentTicks = 0

        self._sbar.valueChanged.connect(self._onValueChanged)

    @property
    def minimum(self):
        return self._min

    @property
    def maximum(self):
        return self._max

    @property
    def pageStep(self):
        return self._pageStep

    @property
    def singleStep(self):
        return self._singleStep

    @property
    def value(self):
        return self._exactValue

    @minimum.setter
    def minimum(self, value):
        if self._min != value:
            self._min = value
            if self._exactValue < self._min:
                self._exactValue = self._min
            self._update()
            self.rangeChanged.emit(self._min, self._max)

    @maximum.setter
    def maximum(self, value):
        if self._max != value:
            self._max = value
            if self._exactValue > self._max:
                self._exactValue = self._max
            self._update()
            self.rangeChanged.emit(self._min, self._max)

    @pageStep.setter
    def pageStep(self, value):
        if self._pageStep != value:
            self._pageStep = value
            self._update()

    @singleStep.setter
    def singleStep(self, value):
        if self._singleStep != value:
            self._singleStep = value
            self._update()

    @value.setter
    def value(self, new_value):
        if self._exactValue != new_value:
            new_value = max(self._min, min(self._max, new_value))
            self._exactValue = new_value
            # do not touch Qt scrollbar if its value should not change
            if self._valueToTicks(new_value) != self._currentTicks:
                self._update()
            self.valueChanged.emit(self._exactValue)

    def update(self, value=None, minimum=None, maximum=None, pageStep=None, singleStep=None):
        for param, param_value in (('minimum', minimum), ('maximum', maximum), ('pageStep', pageStep),
                             ('singleStep', singleStep), ('value', value)):
            if param_value is not None:
                setattr(self, param, param_value)

    def _update(self):
        if self._max - self._min + 1 > MaximumTickCount:
            self._sbar.setMaximum(MaximumTickCount)
        else:
            self._sbar.setMaximum(self._max - self._min)
        self._sbar.setPageStep(max(1, self._valueToTicks(self._pageStep)))
        self._sbar.setSingleStep(max(1, self._valueToTicks(self._singleStep)))
        self._currentTicks = self._valueToTicks(self._exactValue)
        self._sbar.setValue(self._currentTicks)

    @property
    def _tickValue(self):
        return (self._max - self._min + 1) / MaximumTickCount

    def _ticksToValue(self, ticks):
        if self._max - self._min + 1 > MaximumTickCount:
            tick_start_value = self._min + ticks * self._tickValue
            value = math.ceil(tick_start_value)
            assert(tick_start_value <= value < tick_start_value + self._tickValue)
            return value
        return ticks + self._min

    def _valueToTicks(self, value):
        if self._max - self._min + 1 > MaximumTickCount:
            value = max(self._min, min(self._max, value))
            return math.floor((value - self._min) / self._tickValue)
        return value - self._min

    def _onValueChanged(self, new_ticks):
        if new_ticks != self._currentTicks:
            if new_ticks == MaximumTickCount:
                self._exactValue = self._max
            else:
                self._exactValue = self._ticksToValue(new_ticks)
            self._currentTicks = new_ticks
            self.valueChanged.emit(self._exactValue)
