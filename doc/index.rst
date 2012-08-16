.. Poni documentation master file, created by
   sphinx-quickstart on Sat Dec  4 17:47:18 2010.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Poni's documentation!
================================

Poni is a systems management tool for defining, deploying and verifying complex
multi-node computer systems.

Overview
--------
Poni helps managing systems in many ways:

* Systems, nodes, installed software and settings are stored in a central Poni
  repository, so there is a single location where the system is defined and documented
* Changes to the Poni repository can be version-controlled with Git_ allowing rollback
  and access to history of configuration changes
* Applications are configured by rendering configuration templates, using a powerful
  template language (such as Cheetah_) reducing the need to write application-specific
  installation or configuration scripts
* The entire system configuration is available when creating node-specific configuration
  files, making it easy to wire multiple nodes together
* Virtual machines can be easily provisioned from a cloud provider (currently
  `Amazon EC2`_ is supported)

Contents
--------

.. toctree::
   :maxdepth: 2

   overview
   changes
   getting-started
   properties
   modify
   template-variables
   plugins
   ec2
   vsphere
   remote
   vc
   examples/puppet

..
  Indices and tables
  ==================

  * :ref:`genindex`
  * :ref:`modindex`
  * :ref:`search`

.. include:: definitions.rst
