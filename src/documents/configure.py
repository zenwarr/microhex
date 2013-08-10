import os
import sys
from PyQt4 import pyqtconfig

if len(sys.argv) < 2:
    raise RuntimeError('output directory was not specified!')
else:
    build_dir = os.path.normpath(sys.argv[1])

defines = sys.argv[2:]

sources_dir = os.path.dirname(__file__)
build_file = os.path.join(build_dir, "documents.sbf")
install_dir = os.path.join(os.path.dirname(sources_dir), 'hex')

config = pyqtconfig.Configuration()
os.system(' '.join((config.sip_bin, '-c', build_dir, '-b', build_file, '-g', '-e',
          '-I', config.pyqt_sip_dir, config.pyqt_sip_flags, os.path.join(sources_dir, 'documents.sip'))))

makefile = pyqtconfig.QtGuiModuleMakefile(configuration=config, build_file=build_file,
                                           dir=build_dir, makefile='Makefile-sip', install_dir=install_dir)
makefile.extra_cxxflags = ['-std=c++0x']
makefile.extra_libs = ['documents']
makefile.extra_lib_dirs = ['.']
makefile.extra_include_dirs.append(sources_dir)
makefile.extra_defines += defines
makefile.generate()
