import os
from PyQt4 import pyqtconfig

build_file = "documents.sbf"

config = pyqtconfig.Configuration()
os.system(' '.join((config.sip_bin, '-c', '.', '-b', build_file,
          '-I', config.pyqt_sip_dir, config.pyqt_sip_flags, 'documents.sip')))

makefile = pyqtconfig.QtCoreModuleMakefile(configuration=config,
                                          build_file=build_file)
makefile.extra_cxxflags = ['-std=c++0x']
makefile.extra_libs = ['documents']
makefile.extra_lib_dirs = ['.']
makefile.generate()
