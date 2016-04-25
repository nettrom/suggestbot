import os

from setuptools import find_packages, setup

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

def requirements(fname):
    for line in open(os.path.join(os.path.dirname(__file__), fname)):
        yield line.strip()

setup(
    name="suggestbot",
    version="0.1.0", 
    author="SuggestBot Dev Group / Morten Warncke-Wang",
    author_email="nettrom@gmail.com",
    description=("A library for recommeding Wikipedia articles"),
    license="LGPL",
    url="https://github.com/nettrom/suggestbot",
    packages=find_packages(),
    entry_points={},
    long_description=read('README.md'),
    install_requires=list(requirements('requirements.txt')),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Lesser General Public License v2 (LGPLv2)",
        "Operating System :: OS Independent"
    ],
)
