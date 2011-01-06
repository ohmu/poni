===========
Poni readme
===========

Overview
========
Poni is a simple system configuration management tool implemented in Python_.

General Information
===================
:documentation: http://melor.github.com/poni/
:source repo: https://github.com/melor/poni
:pypi: http://pypi.python.org/pypi/poni
:email: mika dot eloranta at gmail dot com
:bug tracker: https://github.com/melor/poni/issues

Pre-requisites
==============

Installing and operating Poni requires:

* Python_ 2.6 (or greater)
* setuptools_ installed
* Internet connection for downloading the dependency Python packages from PyPI_

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
* Sphinx_

.. _ReST: http://docutils.sourceforge.net/rst.html
.. _docutils: http://pypi.python.org/pypi/docutils

Installation
============
NOTE: during installation the following packages and their dependencies are
automatically installed from PyPI_:

* `path.py`_ (directory and file management)
* Cheetah_ (text-based templating language)
* Argh_ (command-line argument parsing)

Installing the following Python libraries will add optional functionality:

* Paramiko_ (Remote node control using SSH)
* GitPython_ (Version controlling the repository with Git)
* Boto_ (`Amazon EC2`_ virtual machine provisioning)
* Genshi_ (XML-based templating)

.. _`Amazon EC2`: http://aws.amazon.com/ec2/
.. _Paramiko: http://pypi.python.org/pypi/paramiko
.. _Boto: http://pypi.python.org/pypi/boto
.. _`path.py`: http://pypi.python.org/pypi/path.py
.. _Argh: http://pypi.python.org/pypi/argh
.. _GitPython: http://pypi.python.org/pypi/GitPython
.. _Cheetah: http://pypi.python.org/pypi/Cheetah
.. _Genshi: http://pypi.python.org/pypi/Genshi
.. _Sphinx: http://sphinx.pocoo.org/

Installation using pip or easy_install
--------------------------------------
Poni can be installed from Python Package Index (PyPI) by running ``pip install poni`` or
``easy_install poni``.

Manual Installation steps
-------------------------
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
Please refer to the documentation under the ``doc/`` directory
(published at http://melor.github.com/poni/) and to the example systems under the
``examples/`` directory.

License (MIT)
=============
::

  Copyright (c) 2010 Mika Eloranta

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
