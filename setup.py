#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

setup(
    name='testalchemy',
    version='0.4',
    author='Tim Perevezentsev',
    author_email='riffm2005@gmail.com',
    url='https://github.com/riffm/testalchemy',
    description='A set of utility classes for testing code that uses sqlalchemy',
    license='MIT',
    install_requires=['sqlalchemy'],
    py_modules=['testalchemy'],
    test_suite='tests',
    platforms='Any'
)
