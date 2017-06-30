#!/usr/bin/env python3

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
