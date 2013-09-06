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
* Argh_ (command-line argument parsing)

Installing the following Python libraries will add optional functionality:

* Cheetah_ (text-based templating language)
* Genshi_ (XML-based templating language)
* Mako_ (text-based templating language)
* Paramiko_ (Remote node control using SSH)
* GitPython_ (Version controlling the repository with Git)
* Boto_ (`Amazon EC2`_ virtual machine provisioning)
* pyvsphere_ (VMWare virtual machine provisioning)
* libvirt-python_ (libvirt virtual machine provisioning)
* PyDNS_ (libvirt provisioning dependency)
* lxml_ (libvirt provisioning dependency)

.. _`Amazon EC2`: http://aws.amazon.com/ec2/
.. _Paramiko: http://pypi.python.org/pypi/paramiko
.. _Boto: http://pypi.python.org/pypi/boto
.. _`path.py`: http://pypi.python.org/pypi/path.py
.. _Argh: http://pypi.python.org/pypi/argh
.. _GitPython: http://pypi.python.org/pypi/GitPython
.. _Cheetah: http://pypi.python.org/pypi/Cheetah
.. _Mako: http://www.makotemplates.org/
.. _Genshi: http://pypi.python.org/pypi/Genshi
.. _Sphinx: http://sphinx.pocoo.org/
.. _pyvsphere: https://github.com/F-Secure/pyvsphere
.. _libvirt-python: http://libvirt.org/python.html
.. _PyDNS: http://pydns.sourceforge.net/
.. _lxml: http://lxml.de/

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

Credits
=======
Thanks for the contributions!

* Oskari Saarenmaa (features)
* Santeri Paavolainen (fixes)
* Lakshmi Vyas (new features for AWS-EC2 support)
* Lauri Heiskanen (enabling pseudo-tty)
* F-Secure Corporation (major improvements, VMWare vSphere and libvirt support)

License (Apache 2.0)
====================
This package is licensed under the open-source "Apache License, Version 2.0".

The full license text is available in the file ``LICENSE`` and at
http://www.apache.org/licenses/LICENSE-2.0.txt

**Note:** poni versions older than 0.6 were licensed under the MIT license.
