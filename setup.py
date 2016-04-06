from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='pytia',
    version='0.1.0',
    description='TOBI interface A server and client',
    long_description=long_description,
    url='https://github.com/andrewramsay/pytia',
    author='Andrew Ramsay',
    author_email='andrew.ramsay@glasgow.ac.uk',
    
    license='MIT',

    classifiers=[
        'Development Status :: 4 - Beta',

        'Intended Audience :: Developers',
        
        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],

    keywords='tobi tia acquisition signals',

    py_modules=['pytia'],

    install_requires=[],
)

