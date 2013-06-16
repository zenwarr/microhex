import hex.settings as settings


_is_registered = False


def doRegister():
    global _is_registered

    if not _is_registered:
        _settings_to_register = (
            ('integeredit.uppercase', False, bool),
            ('integeredit.default_style', 'c', str),
            ('files.max_memoryload_size', 1024 * 1024 * 10, int)
        )

        s = settings.globalSettings()
        for key, default, required_type in _settings_to_register:
            s.register(key, default, required_type)
        _is_registered = True
