# The MIT License
#
# Copyright (c) 2013 zenwarr
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""This module provides functionality to read and store application settings. All settings are stored
in JSON format, and syntax parsing implemented with standard JSON module, having all its advantages and
lacks. For example, it cannot store binary data.
Before using module functions you should configure it. Configuring is done by initializing four variables:
    defaultSettingsFilename is filename (without path) for Settings object returned by globalSettings
    function.
    defaultQuickSettingsFilename is filename (without path) for Settings object returned by globalQuickSettings
    function.
    defaultSettingsDirectory is directory path where settings files are be stored if you do not specify
    absolute path for paths.
    warningOutputRoutine is method module code will call when some non-critical errors are found.
Or you can use defaultConfigure function passing application name to it.

Example:

    import settings
    import logging

    # ...
    logger = logging.getLogger(__name__)
    # ...

    # application initialization
    settings.defaultConfigure('MyApplication')
    settings.warningOutputRoutine = logger.warn

    # ...

    # register application settings
    s = settings.globalSettings()
    s.register('god_mode', False)

    # ...

    # read
    is_in_god_mode = s['god_mode']

    # save
    s['god_mode'] = is_in_god_mode

    # reset one setting to default value
    del s['god_mode']

    # reset all settings
    s.reset()

Each Settings object can be in strict mode or not. When object is in strict mode, it allows writing only
registered settings. Default values can be used only with strict Settings object.
"""

__author__ = 'zenwarr'


import os
import sys
import json
import threading
import copy
from PyQt4.QtCore import QObject, pyqtSignal
import hex.utils as utils


class SettingsError(Exception):
    pass


def defaultConfigure(app_name):
    global defaultSettingsFilename, defaultQuickSettingsFilename, defaultSettingsDirectory

    defaultSettingsFilename = app_name + '.conf'
    defaultQuickSettingsFilename = app_name + '.qconf'

    if sys.platform.startswith('win'):
        defaultSettingsDirectory = os.path.expanduser('~/Application Data/' + app_name)
    elif sys.platform.startswith('darwin'):
        defaultSettingsDirectory = os.path.expanduser('~/Library/Application Support/' + app_name)
    else:
        defaultSettingsDirectory = os.path.expanduser('~/.' + app_name)


defaultSettingsFilename = ''
defaultQuickSettingsFilename = ''
defaultSettingsDirectory = ''
warningOutputRoutine = None


class Settings(QObject):
    settingChanged = pyqtSignal(str, object)

    def __init__(self, filename, strict_control=False):
        QObject.__init__(self)
        self.lock = threading.RLock()
        self.__filename = filename
        self.allSettings = {}
        self.registered = {}
        self.__strictControl = strict_control
        self.__broken = False

    @property
    def filename(self):
        return self.__filename if os.path.isabs(self.__filename) else os.path.join(defaultSettingsDirectory, self.__filename)

    def load(self):
        """Reloads settings from configuration file. If settings filename does not exist or empty, no error raised
        (assuming that all settings has default values). But if file exists but not accessible, SettingsError
        will be raised. Invalid file structure also causes SettingsError to be raised.
        Stored keys that are not registered will cause warning message, but it is not critical error (due
        to compatibility with future versions and plugins). Unregistered settings are placed in allSettings dictionary
        as well as registered ones.
        """

        with self.lock:
            self.allSettings = {}

            if not os.path.exists(self.filename):
                return

            try:
                with open(self.filename, 'rt') as f:
                    # test file size, if zero - do nothing
                    if not os.fstat(f.fileno()).st_size:
                        return

                    try:
                        settings = json.load(f)
                    except ValueError as err:
                        raise SettingsError('error while parsing config file {0}: {1}'.format(self.filename, err))

                    if not isinstance(settings, dict):
                        raise SettingsError('invalid config file {0} format'.format(self.filename))

                    for key, value in settings.items():
                        if self.__strictControl:
                            if key not in self.registered:
                                if warningOutputRoutine is not None:
                                    warningOutputRoutine('unregistered setting in config file {0}: {1}'.format(self.filename, key))
                            else:
                                required_type = self.registered[key].requiredType
                                if required_type and not isinstance(value, required_type):
                                    if warningOutputRoutine is not None:
                                        warningOutputRoutine('setting {0} has wrong type {1} ({2} required)'.format(key, type(value), required_type))
                                    value = self.registered[key].default
                        self.allSettings[key] = value
            except Exception as err:
                self.__broken = True
                raise SettingsError('failed to load settings: {0}'.format(err))

    def save(self, keep_unregistered=True):
        """Store all settings into file.
        If :keep_unregistered: is True, settings that present in target file but not in :registered: dictionary
        will be kept. Otherwise all information stored in target file will be lost. If target file is not valid
        settings file, it will be overwritten. If not in strict mode, :keep_unregistered: has no effect: all settings
        that are not in :allSettings: will be kept.
        All settings in :allSettings: will be stored, even not registered ones.
        Method creates path to target file if one does not exist.
        """

        with self.lock:
            try:
                utils.makedirs(os.path.dirname(self.filename))

                if self.__broken:
                    # if we failed to load settings from this file, it is possible that file syntax is incorrect.
                    # To prevent loss of settings we rename old settings file to something like
                    # "myapp.conf.broken-2013-03-30 21:45:15.878632".
                    import datetime
                    while True:
                        new_filename = self.filename + '.broken-' + str(datetime.datetime.now())
                        if not os.path.exists(new_filename):
                            break

                    try:
                        os.rename(self.filename, new_filename)
                    except OSError as err:
                        if warningOutputRoutine is not None:
                            warningOutputRoutine('failed to copy broken settings file {0} -> {1}'.format(self.filename, new_filename))

                    warningOutputRoutine('broken settings file was stored with {0} name'.format(new_filename))
                    self.__broken = False

                with open(self.filename, 'w+t') as f:
                    settings = self.allSettings

                    if not self.__strictControl or keep_unregistered:
                        try:
                            saved_settings = json.load(f)
                        except ValueError:
                            saved_settings = None

                        if isinstance(saved_settings, dict):
                            for key, value in saved_settings:
                                if not self.__strictControl:
                                    if key not in self.allSettings:
                                        settings[key] = saved_settings[key]
                                else:
                                    if key not in self.registered:
                                        settings[key] = saved_settings[key]

                    json.dump(settings, f, ensure_ascii=False, indent=4)
            except Exception as err:
                raise SettingsError('failed to save settings: {0}'.format(err))

    def reset(self):
        """Reset all settings to defaults. Unregistered ones are not changed. Note that this method does not
        requires save to be called to apply changes - it applies changes itself by deleting configuration files.
        """

        with self.lock:
            if os.path.exists(self.filename):
                os.remove(self.filename)

            changed_settings = self.allSettings.keys()
            self.allSettings = {}
            if self.__strictControl:
                for changed_setting in changed_settings:
                    if changed_setting in self.registered:
                        self.settingChanged.emit(changed_setting, self.defaultValue(changed_setting))

    def resetSetting(self, setting_name):
        """Reset only single setting to its default value. SettingsError raised if this setting is not registered.
        If not in strict mode, removes key with given name.
        """

        with self.lock:
            if self.__strictControl and setting_name not in self.registered:
                raise SettingsError('writing unregistered setting %s' % setting_name)
            if setting_name in self.allSettings:
                del self.allSettings[setting_name]
                if self.__strictControl:
                    self.settingChanged.emit(setting_name, self.defaultValue(setting_name))

    def get(self, setting_name):
        """Return value of setting with given name. In strict mode, trying to get value of unregistered setting that does not exist
        causes SettingsError. You still can get value of unregistered settings that was loaded from file.
        If not in strict mode, returns None for settings that does not exist.
        """

        with self.lock:
            if setting_name in self.allSettings:
                return copy.deepcopy(self.allSettings[setting_name])
            elif setting_name in self.registered:
                return copy.deepcopy(self.registered[setting_name].default)
            elif self.__strictControl:
                raise SettingsError('reading unregistered setting %s' % setting_name)
            else:
                return None

    def defaultValue(self, setting_name):
        """Return default value for given setting. Raises SettingsError for settings that are not registered.
        Returns None for non-existing settings if not in strict mode.
        """

        with self.lock:
            if setting_name in self.registered:
                default = self.registered[setting_name].default
                return default() if utils.isCallable(default) else copy.deepcopy(default)
            elif self.__strictControl:
                raise SettingsError('reading unregistered setting %s' % setting_name)
            else:
                return None

    def set(self, setting_name, value):
        """Set value for given setting. In strict mode, writing value for setting that does not exist raises
        SettingsError (although you still can modify such values with direct access to allSettings dict).
        """

        with self.lock:
            if self.__strictControl:
                if setting_name not in self.registered:
                    raise SettingsError('writing unregistered setting %s' % setting_name)
                else:
                    required_type = self.registered[setting_name].requiredType
                    if required_type and not isinstance(value, required_type):
                        raise SettingsError('writting setting {0} with wrong type {1} ({2} expected)'.format(
                            setting_name, type(value), required_type
                        ))

            if setting_name in self.registered and self.registered[setting_name].default == value:
                if setting_name in self.allSettings:
                    del self.allSettings[setting_name]
            else:
                self.allSettings[setting_name] = value

            if self.__strictControl:
                self.settingChanged.emit(setting_name, copy.deepcopy(value))

    def register(self, setting_name, default_value=None, required_type=None):
        """Register setting with specified name, given default value and required type. required_type argument can
        be tuple of types.
        """

        with self.lock:
            if setting_name not in self.registered:
                class SettingData(object):
                    def __init__(self, default, required_type):
                        self.default = default
                        self.requiredType = required_type

                self.registered[setting_name] = SettingData(default_value, required_type)
            elif self.registered[setting_name] != default_value:
                raise SettingsError('cannot register setting {0}: another one registered with this name'
                                    .format(setting_name))

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)

    def __delitem__(self, key):
        self.resetSetting(key)


_globalSettings = None
_globalQuickSettings = None


def globalSettings():
    """Return settings object used to store user-customizable parameters. It is in strict mode.
    """

    global _globalSettings
    if _globalSettings is None:
        # under tests we should always return default values for all settings without reading
        # configuration file. This is possible only if strict_control is disabled.
        _globalSettings = Settings(defaultSettingsFilename, strict_control=True)
    return _globalSettings


def globalQuickSettings():
    """Return settings object used to store application information that should not be edited by user.
    (just like list of opened file, search history, window sizes and positions, etc)
    """

    global _globalQuickSettings
    if _globalQuickSettings is None:
        _globalQuickSettings = Settings(defaultQuickSettingsFilename)
    return _globalQuickSettings
