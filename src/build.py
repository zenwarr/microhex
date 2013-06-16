#!/usr/bin/python3

import sys
import os


class Builder:
    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.ignore_dirs = ['__pycache__', 'data']

        if sys.platform.startswith('win32'):
            self.pyqt4_path = os.path.join(os.path.dirname(sys.executable), 'Lib\\site-packages\\PyQt4')
            self.uic_path = os.path.join(self.pyqt4_path, 'pyuic4')
            self.rcc_path = os.path.join(self.pyqt4_path, 'pyrcc4')
            self.lrelease_path = os.path.join(self.pyqt4_path, 'lrelease')
        else:
            self.uic_path = 'pyuic4'
            self.rcc_path = 'pyrcc4'
            self.lrelease_path = 'lrelease'

    def build(self):
        print('BUILDING......')
        for dirpath, dirs, files in os.walk(self.project_dir):
            if os.path.basename(dirpath) not in self.ignore_dirs:
                for name in files:
                    path = os.path.join(dirpath, name)
                    name, ext = os.path.splitext(name)
                    if ext == '.ui':
                        self.processFile(path, 'ui_{0}.py', '{0} -i 0 -o {2} {1}', 'uic')
                    elif ext == '.qrc':
                        self.processFile(path, 'qrc_{0}.py', '{0} -py3 -o {2} {1}', 'rcc')
                    elif ext == '.ts':
                        self.processFile(path, '{0}.qm', '{0} {1} -qm {2}', 'lrelease')
        print('BUILDING DONE')

    def processFile(self, path, gen_filename_pattern, tool_command_pattern, op_name):
        f, e = os.path.splitext(os.path.basename(path))
        gen_file = os.path.join(os.path.dirname(path), gen_filename_pattern.format(f))
        if self.need_update(path, gen_file):
            print("{0}'ing {1} -> {2}".format(op_name, f, gen_file))
            tool_path = getattr(self, op_name + '_path')
            os.system(tool_command_pattern.format(tool_path, path, gen_file))

    def need_update(self, source, generated):
        return not os.path.exists(generated) or os.stat(source).st_mtime > os.stat(generated).st_mtime


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('should get 1 argument: path to project directory')
        sys.exit(1)

    builder = Builder(sys.argv[1])
    builder.build()
