# Spitfire - a Python-C++ library for building tabulated chemistry models and solving differential equations                    
# Copyright 2019 National Technology & Engineering Solutions of Sandia, LLC (NTESS). 
#                       
# You should have received a copy of the 3-clause BSD License                                        
# along with this program.  If not, see <https://opensource.org/licenses/BSD-3-Clause>.   
#                    
# Questions? Contact Mike Hansen (mahanse@sandia.gov)    

import os
from distutils.core import setup
from distutils.extension import Extension
from sys import argv as command_line_args
from sys import executable as python_cmd
from Cython.Build import cythonize
from numpy import get_include as numpy_include
import platform


def readfile(filename):
    try:
        with open(filename) as f:
            return f.read()
    except:
        with open(filename, encoding='utf-8') as f:
            return f.read()


griffon_build_dir = None
for arg in command_line_args:
    if 'griffon-build-dir' in arg:
        griffon_build_dir = arg.split('griffon-build-dir=')[1]
        command_line_args.remove(arg)

if griffon_build_dir is None:
    raise ValueError(
        'Error in installing Spitfire. The command line argument "--griffon-build-dir=[]" must be provided.')

cython_extra_compile_args = ['-O3', '-g', '-std=c++11']

is_mac = platform.system() == 'Darwin'
if is_mac:
    cython_lapack_lib = []
    cython_lapack_extra = ['-framework', 'Accelerate', '-mmacosx-version-min=10.12']
    cython_extra_compile_args += ['-stdlib=libc++']
else:
    cython_lapack_lib = ['blas', 'lapack']
    cython_lapack_extra = []

cython_include_directories = [numpy_include(),
                              os.path.join(griffon_build_dir, 'include')]
cython_library_directories = [os.path.join(griffon_build_dir, 'lib')]
cython_libraries = ['griffon_cpp'] + cython_lapack_lib

griffon_cython = cythonize(Extension(name='spitfire.griffon.griffon',
                                     sources=[os.path.join('spitfire', 'griffon', 'griffon.pyx')],
                                     extra_compile_args=cython_extra_compile_args,
                                     include_dirs=cython_include_directories,
                                     library_dirs=cython_library_directories,
                                     libraries=cython_libraries,
                                     extra_link_args=cython_lapack_extra,
                                     language='c++'))

setup(name='Spitfire',
      version=readfile('version'),
      author='Michael A. Hansen',
      author_email='mahanse@sandia.gov',
      license=readfile('license.md'),
      description=readfile('description_short'),
      long_description=readfile('readme.md'),
      packages=['spitfire.chemistry', 'spitfire.time', 'spitfire.griffon'],
      ext_modules=griffon_cython,
      package_data={'spitfire.griffon': ['*.so']})

html_path = os.path.join(os.getcwd(), 'spitfire_docs', 'build', 'html', 'index.html')

print('- done installing Spitfire!')
unit_test_line = f'{python_cmd} -m unittest discover -s spitfire_test/'
docs_line = 'cd spitfire_docs; make html; make latexpdf; cd ..'
docs_html = f'open in a browser: file://{html_path}'

print(f'- Run the tests              : {unit_test_line}')
print(f'- Build the documentation    : {docs_line}')
print(f'- View the html documentation: {docs_html}\n')
