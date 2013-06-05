from PyQt4.QtGui import QCommonStyle, QPalette


class ProxyStyle(QCommonStyle):
    def __init__(self, base):
        QCommonStyle.__init__(self)
        self._base = base

    def drawComplexControl(self, control, option, painter, widget = None):
        return self._base.drawComplexControl(control, option, painter, widget)

    def drawControl(self, element, option, painter, widget = None):
        return self._base.drawControl(element, option, painter, widget)

    def drawItemPixmap(self, painter, rectangle, alignment, pixmap):
        return self._base.drawItemPixmap(painter, rectangle, alignment, pixmap)

    def drawItemText(self, painter, rectangle, alignment, palette, enabled, text, textRole = QPalette.NoRole):
        return self._base.drawItemText(painter, rectangle, alignment, palette, enabled, text, textRole)

    def drawPrimitive(self, element, option, painter, widget = None):
        return self._base.drawPrimitive(element, option, painter, widget)

    def generatedIconPixmap(self, iconMode, pixmap, option):
        return self._base.generatedIconPixmap(iconMode, pixmap, option)

    def hitTestComplexControl(self, control, option, position, widget = None):
        return self._base.hitTestComplexControl(control, option, position, widget)

    def itemPixmapRect(self, rectangle, alignment, pixmap):
        return self._base.itemPixmapRect(rectangle, alignment, pixmap)

    def itemTextRect(self, metrics, rectangle, alignment, enabled, text):
        return self._base.itemTextRect(metrics, rectangle, alignment, enabled, text)

    def pixelMetric(self, metric, option = None, widget = None):
        return self._base.pixelMetric(metric, option, widget)

    def polish(self, *args, **kwargs):
        return self._base.polish(*args, **kwargs)

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        return self._base.styleHint(hint, option, widget, returnData)

    def subControlRect(self, control, option, subControl, widget = None):
        return self._base.subControlRect(control, option, subControl, widget)

    def subElementRect(self, element, option, widget = None):
        return self._base.subElementRect(element, option, widget)

    def unpolish(self, *args, **kwargs):
        return self._base.unpolish(*args, **kwargs)

    def sizeFromContents(self, ct, opt, contentsSize, widget = None):
        return self._base.sizeFromContents(ct, opt, contentsSize, widget)
