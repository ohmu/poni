==============
Poni Changelog
==============

Version 0.7.0
=============
:release date: TBD

* added ``--exclude PATTERN`` support for many commands: allows skipping nodes
  that match a pattern when e.g. running a remote command over multiple nodes
* optimization: internal cache for loaded plugin modules
* ``add_file()`` supports ``owner=uid`` and ``group=gid`` optional args
* AWS security groups can be set via ``cloud.security_group``
  **(thanks, Lakshmi!)**
* ``cloud ip`` command for assigning an AWS Elastic IP for a node
  **(thanks, Lakshmi!)**
* remote operations support ``pseudo_tty=True`` for allocating a ptty for
  the operation **(thanks, Lauri!)**
* control command node logs include the ``BEGIN`` and ``END`` tags
* render also ``source_path`` as a template
* bugfix: ``poni script`` handles files with multi-line commands with comments
  in the middle
* bugfix: fixed listing settings from a root-level node
* bugfix: fixed "poni control" dependency ops being added multiple times (fixes
  huge memory usage when running complex operations over tens of servers)

Version 0.5.0
=============
:release date: 2011-07-12

* added ``add_file()`` support for ``dest_bucket`` argument: allows rendering
  templates into buckets instead of deploying them to target file paths
* bugfix: add extra lib paths to sys.path only once
* bugfix: full stdout/stderr is now read from remote ssh commands
* bugfix: hierarchical settings overrides

Version 0.4.9
=============
:release date: 2011-04-05

* minor fixes

Version 0.4.8
=============
:release date: 2011-04-03

* made "control" operation errors stand out better by color highlighting
* print remote operation tag lines in one piece to make output cleaner in
  multi-threaded ops
* bugfix: load plugins to separate modules
* added explicit deployment handling for ENOENT files
* ``deploy`` command reports status at the end
* added ``$record()`` method for templates
* added configrable ssh connect timeout property: ``ssh-timeout:int=N``
* bugfix: skip trying file deployment if checking existing file fails
* tuned down unnecessary paramiko ERROR level logging
* added full_path property to ``Item``; renamed ``Config.full_name`` to
  ``full_path``
* bugfix: verify/audit final file count

Version 0.4.7
=============
:release date: 2011-03-20

* bugfix: audit reports number of errors properly
* added Node.addr(network) method for getting the node address for a given
  network
* added ``--quiet`` and ``--output-dir`` args for remote ops
* bugfix: logging bug in update-config when used with --verbose flag

Version 0.4.6
=============
:release date: 2011-03-09

* added summary output line for ``audit`` command
* prefix remote command output lines with [nodename]
* added ``Config.full_name`` property
* hashable Node, System and Config
* bugfix: paramiko no output warning timeout fix

Version 0.4.5
=============
:release date: 2011-02-22

* bugfix: added set_combine_stderr(True) for paramiko, tuned rx loop

Version 0.4.4
=============
:release date: 2011-02-20

* operations can be timed (``poni --clock`` or ``control --clock-tasks``) and
  results stored in a log file (``--time-log FILE``), reports printed out with
  ``poni --time-log FILE report``
* added warning messages for ``control`` tasks that do not send output in a
  long while, kill jobs after five minutes of inactivity
* added support for ``optional_requires`` task dependencies, such tasks are not
  required to exist but are guaranteed to be run before the dependent task
* ``deploy`` post-process actions are run even if file is unchanged
* bugfix: paramiko ssh connection error is reported neatly
* bugfix: various small fixes

Version 0.4.3
=============
:release date: 2011-01-25

* control tasks can be run without dependent tasks with ``--no-deps``
* bugfix: control tasks with in ``script`` files
* bugfix: Tool.execute() exit code check

Version 0.4.2
=============
:release date: 2011-01-23

* added ``poni add-library`` command for specifying directories (that can be
  within Poni configs) which are added to the Python ``sys.path`` accessible
  by Poni plugins
* requires GitPython>=0.3.1 and Cheetah>=2.4.2

Version 0.4.1
=============
:release date: 2011-01-11

* bugfix: ``remote exec`` process exit code is now properly checked
* better error messages for failed ``poni control`` commands

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
