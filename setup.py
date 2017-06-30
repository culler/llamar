#!/usr/bin/env python3

import sys
assert sys.version_info.major==3, 'This is a Python 3 module.'

from setuptools import setup

setup(name='LLamar',
      version='1.0',
      description='LLMNR implementation',
      author='Marc Culler',
      url='https://bitbucket.org/marc_culler/llamar/',
      license='GPLv2+',
      packages=['llmnr'],
      entry_points = {'console_scripts': ['busco = llmnr.busco:main',
                                          'llmnr = llmnr.responder:main']},
     )
