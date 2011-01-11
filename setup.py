from setuptools import setup, find_packages
import version

# temporary chdir is needed so that scons can build this from another cwd
import os
old_dir = os.getcwd()
new_dir = os.path.dirname(__file__)
if new_dir:
    os.chdir(new_dir)
else:
    new_dir = "."

long_desc = file("%s/README.rst" % new_dir).read()

depends = [
    "path.py>=2.2.2",
    "paramiko>=1.7.6",
    "cheetah>=2.4.2",
    "GitPython>=0.3.1",
    "argh>=0.13",
    ]

try:
    import json
except ImportError:
    depends.append("simplejson")

try:
    import argparse
except ImportError:
    depends.append("argparse")


setup(
    name = 'poni',
    version = version.get_project_version("poni/version.py"),
    description = 'system configuration software',
    long_description = long_desc,
    author = "Mika Eloranta",
    author_email = "mika.eloranta@gmail.com",
    url = "http://github.com/melor/poni",
    classifiers = [
        "Programming Language :: Python",
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Operating System :: OS Independent",
        "Topic :: System :: Installation/Setup",
        "Topic :: System :: Software Distribution",
        "Topic :: Software Development :: Libraries :: Python Modules",
        ],
    packages = find_packages(),
    zip_safe = False,
    install_requires = depends,
    entry_points = {
        'console_scripts': [
            'poni = poni.tool:Tool.run_exit',
            ]
        }
    )

os.chdir(old_dir)
