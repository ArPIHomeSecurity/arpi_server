from setuptools import setup
from distutils.core import Extension

module = Extension('wiegand_io', sources=['wiegand_io.cpp'],
libraries = ['wiringPi','pthread','rt'],
extra_compile_args=['-lpthread', '-lrt', '-I/usr/local/include', '-L/usr/local/lib','-lwiringPi'])
setup(
        name="wiegand_io",
        version="1.0",
        ext_modules=[module],
        install_requires=["wiringPi"]
)