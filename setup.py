from setuptools import setup, find_packages
import version

# temporary chdir is needed so that scons can build this from another cwd
import os
old_dir = os.getcwd()
new_dir = os.path.dirname(__file__)
if new_dir:
    os.chdir(new_dir)

depends = ["path.py", "paramiko", "cheetah", "boto"]
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
