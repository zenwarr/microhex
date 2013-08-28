from PyQt4.QtGui import QFont


_is_registered = False


App_Translation = 'app.translation'
App_DefaultErrorPolicy = 'app.default_error_policy'
App_PoolOperationLimit = 'app.pool_operation_limit'
IntegerEdit_Uppercase = 'integeredit.uppercase'
IntegerEdit_DefaultStyle = 'integeredit.default_style'
HexWidget_ShowHeader = 'hexwidget.show_header'
HexWidget_DefaultTheme = 'hexwidget.default_theme'
HexWidget_AlternatingRows = 'hexwidget.alternating_rows'
HexWidget_Font = 'hexwidget.font'
HexWidget_BlockCursor = 'hexwidget.block_cursor'
HexWidget_HighlightAlpha = 'hexwidget.highlight_alpha'
HexWidget_RandomColorDistance = 'hexwidget.random_color_distance'
HexWidget_Theme = 'hexwidget.theme'
HexWidget_AutoEditMode = 'hexwidget.auto_edit_mode'

ThemeExtension = '.mixth'


def doRegister():
    import hex.settings as settings

    global _is_registered

    if not _is_registered:
        _settings_to_register = (
            (IntegerEdit_Uppercase, False, bool),
            (IntegerEdit_DefaultStyle, 'c', str),
            (HexWidget_ShowHeader, True, bool),
            (App_Translation, '', str),
            (App_DefaultErrorPolicy, 'ask', str),
            (App_PoolOperationLimit, 10, int),
            (HexWidget_DefaultTheme, dict(), dict),
            (HexWidget_AlternatingRows, True, bool),
            (HexWidget_Font, ('Ubuntu Mono,13,-1,5,50,0,0,0,0,0',
                              'Consolas,12,-1,5,50,0,0,0,0,0',
                              'Courier New,10,-1,5,50,0,0,0,0,0'), (list, tuple, str)),
            (HexWidget_BlockCursor, False, bool),
            (HexWidget_HighlightAlpha, 150, int),
            (HexWidget_RandomColorDistance, 100, int),
            (HexWidget_Theme, '', str),
            (HexWidget_AutoEditMode, True, bool)
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
                if ok and utils.isFontInstalled(stored_font.family()):
                    return stored_font
    return font
