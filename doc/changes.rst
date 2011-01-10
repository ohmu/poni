==============
Poni Changelog
==============

Version 0.4
===========
:release date: 2011-01-10

* ``poni control`` command dependencies using ``provides=["foo"]`` and 
  ``requires=["foo"]``
* parallel execution of "control" commands, runs max one concurrent task per
  host and obeys control command dependencies
* ``remote.execute()`` and ``remote.shell()`` support ``verbose=True/False``
  keyword arg
* updated puppet example to install everything using control commands
* new ``template:bool`` system/node property for disabling control commands
  and config template verification for template nodes
* limiting concurrent ``poni control`` tasks with ``--jobs=N``

Version 0.3.1
=============
:release date: 2010-12-26

* added ``poni require`` command that can be used to specify minimum poni 
  version required by a script, e.g. ``poni require 'poni_version >= "0.3.1"'``

Version 0.3
===========
:release date: 2010-12-25

* Poni is now in Python Package Index: http://pypi.python.org/pypi/poni and
  easy_installable
* syntax change for setting properties, new syntax: 
  ``poni set NODE PROPERTY[:MOD1[:MODN[...]]]=VALUE``
* allow multiple conversions using the ``set`` command, e.g. 
  ``poni set linux/ private.ip:prop:ipv4=node.host`` will get the ``node.host``
  value, resolve it to an ipv4 address and store it to ``private.ip`` 
  (see http://melor.github.com/poni/modify.html#chaining-conversions)
* setting properties supports UUIDs, resolving ipv4 and ipv6 addresses,
  decoding/encoding using Python codecs, JSON encoding/decoding, SI and IEEE
  multiplier suffies (e.g. ``10M`` or ``100Kib``) for numbers
* basic support for custom ``poni control`` commands defined in config 
  plugins (see e.g. ``examples/puppet/puppet-agent/plugin.py``)
* documented functions and variables that are available in templates: 
  http://melor.github.com/poni/template-variables.html
* ``poni deploy/audit --path-prefix=/foo/bar`` now creates sub-directories for 
  each node to prevent conflicts when deploying files from multiple nodes to
  the same directory
* Genshi XML-based template support using ``self.render_genshi_xml`` in 
  plugins
* ``find_config(PATTERN)`` is available in templates, yields matching configs 
  and their nodes
* added ``poni version`` command, displays the poni version number

Version 0.2
===========
:release date: 2010-12-09

* added heaps of docs: http://melor.github.com/poni/
* colored output
* ``poni show --diff`` displays differences between unrendered templates and
  fully rendered templates in diff format
* plugin-objects are visible to templates as ``$plugin``
* config settings are now visible to templates as ``$settings``, deprecated
  ``$s``
* ``poni show --raw`` displays raw, unrendered templates
* ``poni --color=on/off/auto`` controls colored output
* ``poni settings list`` lists config settings and their values
* ``poni settings set`` sets config settings
* ``poni list --line-per-prop`` displays each property on a separate line
* ``poni verify -v`` shows status for each file
* ``poni list`` arguments ``-n`` (show nodes, default), ``-s`` (show systems)
  and ``-c`` (show configs)
* the top-level config is available to templates as ``$config``
* renamed version-control commands: ``commit`` is now ``checkpoint`` and 
  ``status`` is now ``diff``
* added ``--full-match``, ``-M`` to many commands, requires full pattern
  match (e.g. with node names) instead of partial match (which is default)
* ssh connections are retried on failure
* ``poni import DEBFILE`` pulls poni configs from a Debian DEB package
* ``poni cloud wait --state=STATE`` waits until node reaches specified running
  state
* deployment: specifying ``dest_path`` ending in a backslash will use the
  source filename as the deployed filename
* ``poni deploy`` creates all directory levels when deploying a file
* config settings are inherited/loaded from parent configs
* ``poni add-node`` supports ``--copy-props`` (used with ``--inherit NODE``),
  copies all node properties from the source node
* parent node's inherited configs are properly collected and used in deployment
* basic repository version-control support with Git using ``poni vc init``, 
  ``poni vc checkpoint MSG`` and ``poni vc diff`` commands
* ``poni add-config --copy-dir=DIR`` copies config templates, plugins, etc.
  from the given directory

Version 0.1
===========
:release date: 2010-11-28

* Initial version with basic deployment support
