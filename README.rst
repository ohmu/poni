===========
Poni readme
===========

Overview
========
Poni is a simple system configuration management tool implemented in Python_.

General Information
===================
:source repo: https://github.com/melor/poni
:email: mika.eloranta@gmail.com
:bug tracker: https://github.com/melor/poni/issues

Pre-requisites
==============

Installing and operating Poni requires:

* Python_ 2.5 (or greater)
* setuptools_ installed
* Internet connection for downloading the dependent Python packages from PyPI_

.. _Python: http://www.python.org/
.. _setuptools: http://http://pypi.python.org/pypi/setuptools
.. _PyPI: http://pypi.python.org/

Using Amazon EC2 requires setting the following environment variables::

  export AWS_ACCESS_KEY_ID=<your aws access key>
  export AWS_SECRET_ACCESS_KEY=<your aws secret access key>

Additionally, running the included automated tests requires:

* nose_

.. _nose: http://pypi.python.org/pypi/nose

Building HTML files from the included ReST_ documentation requires:

* docutils_

.. _ReST: http://docutils.sourceforge.net/rst.html
.. _docutils: http://pypi.python.org/pypi/docutils

Installation
============
NOTE: during installation the following packages and their dependencies are
automatically installed from PyPI_:

* paramiko_ (SSH)
* boto_ (`Amazon EC2`_)
* `path.py`_ (directory and file management)
* argparse_ (command-line argument parsing)
* cheetah_ (template language)

.. _`Amazon EC2`: http://aws.amazon.com/ec2/
.. _paramiko: http://pypi.python.org/pypi/paramiko
.. _boto: http://pypi.python.org/pypi/boto
.. _`path.py`: http://pypi.python.org/pypi/path.py
.. _argparse: http://pypi.python.org/pypi/argparse
.. _cheetah: http://pypi.python.org/pypi/Cheetah

Installation steps
------------------
1. Unpack the ``poni-v.vv.tar.gz`` package
2. ``cd poni-v.vv/``
3. ``python setup.py install``

Verifying the installation
--------------------------
* You should be able to ``import poni`` from Python
* The ``poni`` command-line tool is installed (to a platform-specific location),
  try running ``poni -h`` for help
* Running automated tests: ``cd poni-v.vv/ && nosetests``

Usage
=====
Please refer to the documentation under the ``doc/`` directory and to the
example systems under the ``examples/`` directory.

License (MIT)
=============
.. include:: LICENSE
   :literal:

