=========================
Developing Config Plugins
=========================

Overview
========
Each config needs to have Python plug-in file that defines the behavior of the
config in different phases of the config's life-cycle.

Plugins can be use to define:

* Individual template configuration files, how they are rendered and where
  are the resulting configuration files deployed
* Deployment-time file copy operations (individual files or recursively 
  copying full directories)
* Custom ``poni control`` operations that provide a convenient (relatively!)
  command-line interface to manipulating the config (e.g. install, start, 
  stop, restart, verify)

Hello World!
============
Here we'll create a simple plugin that illustrates using some of the basic
plugin functionality. The full example can be found in the ``examples/hello``
-directory in the Poni source code package.

First, we'll create a directory for the ``hello`` config and edit 
``hello/plugin.py`` with your favourite file, inserting the following 
contents::

  from poni import config

  class PlugIn(config.PlugIn):
      def add_actions(self):
          self.add_file("hello.txt", mode=0644, dest_path="/tmp/")

Next, edit a new new file ``hello/hello.txt``, to be used as the source
template, and insert the following contents::

  Hello from node $node.name, config $config.name!

Now we have an *amazing* config that can be added to a node and deployed.
Let's create a simple system for testing it out::

  $ poni -d /tmp/hello init
  $ poni -d /tmp/hello add-node batman
  $ poni -d /tmp/hello add-config -d hello/ batman hello-config
  $ poni -d  /tmp/hello list -snc
      node  batman
    config  batman/hello-config
  $ poni -d  /tmp/hello show -v
  --- BEGIN batman: path=/tmp/hello.txt ---
  Hello from node batman, config hello-config!
  
  --- END batman: path=/tmp/hello.txt ---

As can be seen from the above output, the ``$node.name`` and ``$config.name``
template directives were rendered as expected. The difference between the
original template and the fully-rendered one can be shown with the 
``poni show --diff`` -command::

  $ poni -d  /tmp/hello show -v --diff
  --- BEGIN batman: path=/tmp/hello.txt ---
  --- template 
  +++ rendered 
  @@ -1,1 +1,1 @@
  -Hello from node $node.name, config $config.name!
  +Hello from node batman, config hello-config!
  --- END batman: path=/tmp/hello.txt ---


The ``add_actions()`` method is called by Poni to collect deployable files for
each config. 

**TODO:**

* ``add_file()`` arguments
* ``add_dir()`` method

Control Commands
================
Custom commands for controlling deployed configs can be easily added. These
commands are executed by running ``poni control CONFIG-PATTERN COMMAND``,
which executes the ``COMMAND`` for each config that matches the 
``CONFIG-PATTERN``.

Let's add a command for observing the load-averages of the node. Edit the
``hello/plugin.py``, and add the ``loadavg()`` method with just a dummy
print statement for now::

  from poni import config

  class PlugIn(config.PlugIn):
      def add_actions(self):
          self.add_file("hello.txt", mode=0644, dest_path="/tmp/")

      @config.control()
      def loadavg(self, arg):
          print "foo!"

The ``@config.control()`` decorator defines a method as a control command.
These methods are automatically collected by Poni and made available using
the ``poni control`` command. 

Now we can update the changes file to our repository with the 
``update-config`` command and view the available controls with the 
``list -C`` (note: *capital* "C") command::

  $ poni -d /tmp/hello update-config batman/hello-config hello/
  $ poni -d /tmp/hello/ list -C
    config  batman/hello-config
  controls      loadavg

Our loadavg command appears under the ``hello-config``, let's try running it::

  $ poni -d /tmp/hello/ control batman/hello-config loadavg
  foo!
  poni	INFO	all [1] control tasks finished successfully

**TODO:**

* config match patterns (system/node/config, system//config, system//, 
  /config)
* remote execution
* --verbose mode
* ``poni control`` argh parsers, arguments
* control command dependencies
* idempotency
* parallel execution (dependencies, max one concurrent job per host, --jobs=N)


