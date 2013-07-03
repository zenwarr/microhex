import hex.settings as settings
from PyQt4.QtGui import QFont


_is_registered = False


def doRegister():
    global _is_registered

    if not _is_registered:
        _settings_to_register = (
            ('integeredit.uppercase', False, bool),
            ('integeredit.default_style', 'c', str),
            ('files.max_memoryload_size', 1024 * 1024 * 10, int),
            ('hexwidget.show_header', True, bool),
            ('app.translation', '', str),
            ('hexwidget.default_theme', dict(), dict),
            ('hexwidget.alternating_rows', True, bool),
            ('hexwidget.font', ('Ubuntu Mono,13,-1,5,50,0,0,0,0,0',
                                     'Consolas,13,-1,5,50,0,0,0,0,0',
                                     'Courier New,10,-1,5,50,0,0,0,0,0'), (list, tuple, str))
        )

        s = settings.globalSettings()
        for key, default, required_type in _settings_to_register:
            s.register(key, default, required_type)
        _is_registered = True


def getFontFromSetting(setting_data, default_font=None):
    import hex.utils as utils

    font = default_font or QFont()
    if isinstance(setting_data, str):
        stored_font = QFont()
        ok = stored_font.fromString(setting_data)
        return stored_font if ok else font
    elif isinstance(setting_data, (tuple, list)):
        for font_data in setting_data:
            if isinstance(font_data, str):
                stored_font = QFont()
                ok = stored_font.fromString(font_data)
                if ok:
                    return stored_font
    return font
