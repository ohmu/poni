Getting Started with Poni
=========================
Poni is a command-line tool with many different sub-commands for manipulating the
Poni repository and the system nodes.

Let's see the command-line help::

  $ poni -h
  usage: poni [-h] [-D] [-d DIR]

              {audit,set,remote,script,verify,add-system,list,init,vc,add-config,show,import,add-node,deploy,cloud}
              ...

  positional arguments:
    {audit,set,remote,script,verify,add-system,list,init,vc,add-config,show,import,add-node,deploy,cloud}
      list                list systems and nodes
      add-system          add a sub-system
      init                init repository
      import              import nodes/configs
      script              run commands from a script file
      add-config          add a config to node(s)
      set                 set system/node properties
      show                render and show node config files
      deploy              deploy node configs
      audit               audit active node configs
      verify              verify local node configs
      add-node            add a new node
      cloud               cloud operations
      remote              remote operations
      vc                  version-control operations

  optional arguments:
    -h, --help            show this help message and exit
    -D, --debug           enable debug output
    -d DIR, --root-dir DIR
                          repository root directory (default: $HOME/.poni/default)


The default Poni repository directory, unless specified by the ``PONI_ROOT`` environment
variable or by the ``--root-dir DIR`` switch, is ``$HOME/.poni/default``.

Command-specific help can be viewed by executing ``poni <command> -h``, for example::

  $ poni add-system -h
  usage: poni add-system [-h] system

  positional arguments:
    system      system name

  optional arguments:
    -h, --help  show this help message and exit

Creating the Poni Repository
----------------------------
First, we will need to initialize the repository using the ``init`` command::

  $ poni init

There is no output if the command is successful. Most Poni commands will not output much
if there are no errors.

Adding Nodes
------------
A "system" in the Poni context refers to a collection of nodes and/or sub-systems.

Let's say we are defining a system ``webshop`` with four HTTP frontend servers and a
single backend SQL database server. We will divided the ``webshop`` system into two
sub-systems ``frontend`` and ``backend``.

First, we will create the systems::

  $ poni add-system webshop
  $ poni add-system webshop/frontend
  $ poni add-system webshop/backend

Again, no output since everything went ok.

Next, we will add the backend SQL database ``postgres1`` server node into the
``backend`` system::

  $ poni add-node webshop/backend/postgres1

Let's see how the system looks now::

  $ poni list
    node webshop/backend/postgres1

The ``list`` command shows only nodes by default. Let's also view the systems::

  $ poni list -sn
    system webshop
    system webshop/backend
      node webshop/backend/postgres1
    system webshop/frontend

The left column tells the type of the item shown on the right.

The four HTTP frontend nodes can be added with a single command using the ``-n COUNT``
option::


  $ poni add-node "webshop/frontend/http{id}" -n 4
  $ poni list
      node webshop/backend/postgres1
      node webshop/frontend/http1
      node webshop/frontend/http2
      node webshop/frontend/http3
      node webshop/frontend/http4

``-n 4`` tells Poni that four nodes are to be added. Value ranges can also be given, for
example ``-n 5..8`` will create nodes 5, 6, 7 and 8.

The ``{id}`` in the node name gets replaced with the node number. Any normal Python
``string.format()`` formatting codes can be used, too. For example, if you wanted two
digits then ``http{id:02}`` would do the job.

Adding Configs
--------------
A Poni "config" is a configurable item, often a piece of software, than can be added to
a node. A config often contains multiple configuration file templates and a bunch of
settings that will be used in the final configuration files deployed to the nodes. Each
node can have multiple configs applied to them.

Our example DB backend uses PostgreSQL 8.4 as the database  so we will call it ``pg84``.
We can create the config and view it using the ``-c`` option::

  $ poni add-config postg pg84
  $ poni list -nc
      node webshop/backend/postgres1
    config webshop/backend/postgres1/pg84
      node webshop/frontend/http1
      node webshop/frontend/http2
      node webshop/frontend/http3
      node webshop/frontend/http4

Above we were a bit lazy and only wrote ``postg`` above as the target node.

.. note::
  Poni system/node/config arguments are evaluated as regular expressions and will match
  as long as the given pattern appears somewhere in the full name of the target. If there
  are multiple hits, the command will be executed for each of them. Stricter full name
  matching can be enabled by adding the ``-M`` option.

We want to deploy a file describing the DB access permissions named ``pg_hba.conf`` to
the backend node. Use an editor to create a file named ``pg_hba.conf`` with the following contents::

  # This the pg_hba.conf for $node.name
  #
  # TYPE  DATABASE        USER            ADDRESS                 METHOD
  local   all             all                                     trust

Every Poni config needs a ``plugin.py`` file that tells Poni what files need to be
installed and where. Use an editor to create the file with the following contents::

  from poni import config

  class PlugIn(config.PlugIn):
      def add_actions(self):
          self.add_file("pg_hba.conf", dest_path="/etc/postgres/8.4/")

The above plugin will install a single file ``pg_hba.conf`` into the directory
``/etc/postgres/8.4/``.

Now the files can be added into the existing ``pg84`` config::

  $ poni update-config pg84 plugin.py pg_hba.conf -v
  poni    INFO    webshop/backend/postgres1/pg84: added 'plugin.py'
  poni    INFO    webshop/backend/postgres1/pg84: added 'pg_hba.conf'

Now the database node is setup and we can move on to verifying and deployment...

Verifying Configs
-----------------
Checking that there are no problems rendering any of the configs can be done with the
``verify`` command::

  $ poni verify
  poni    INFO    all [1] files ok

No errors reported, good. Let's see how our ``pg_hba.conf`` looks like::

  $ poni show
  --- BEGIN webshop/backend/postgres1: dest=/etc/postgres/8.4/pg_hba.conf ---
  # This is the pg_hba.conf for webshop/backend/postgres1
  #
  # TYPE  DATABASE        USER            ADDRESS                 METHOD
  local   all             all                                     trust

  --- END webshop/backend/postgres1: dest=/etc/postgres/8.4/pg_hba.conf ---

Note that the ``$node.name`` template directive got replaced with the name (full path)
of the node.

Deploying
---------
In order to be able to deploy, Poni needs to know the hostnames of each nodes involved.
For this exercise we'll deploy the files locally instead of copying them over the
network. By default Poni attempts an SSH based deployment::

  $ poni deploy postgres1
  poni    ERROR   RemoteError: webshop/backend/postgres1: 'host' property not set  poni    ERROR   VerifyError: failed: there were 1 errors


Node and system properties can be adjusted with the ``set`` command. We'll set a special
property ``deploy`` to the value ``local`` that tells Poni to install the files to the
local file-system::

  $ poni set postgres1 deploy=local
  $ poni list postgres1 -p
      node webshop/backend/postgres1
      prop     deploy:'local' depth:3 host:'' index:0

The ``list`` option ``-p`` shows node and system properties. In addition to ``host`` there
are a couple of automatically set properties ``depth`` (how deep is the node in the
system hierarchy) and ``index`` (tells the location of the node within its sub-system).

Now deployment can be completed and we'll override the target directory for this exercise
using the ``--path-prefix`` argument, which makes it possible to install all the template files from multiple nodes under a single directory. Sub-directories are added automatically for each system and node level to prevent files from different nodes colliding::

  $ poni deploy postgres1 --path-prefix=/tmp
  manager INFO       WROTE webshop/backend/postgres1: /tmp/webshop/backend/postgres1/etc/postgres/8.4/pg_hba.conf

  $ cat /tmp/webshop/backend/postgres1/etc/postgres/8.4/pg_hba.conf
  # This the pg_hba.conf for webshop/backend/postgres1
  # TYPE  DATABASE        USER            ADDRESS                 METHOD
  local   all             all                                     trust

Auditing
--------
Checking that the deployed configuration is still up-to-date and intact is simple::

  $ poni audit -v --path-prefix=/tmp
  manager	INFO	      OK webshop/backend/postgres1: /tmp/webshop/backend/postgres1/etc/postgres/8.4/pg_hba.conf

Let's see what happens if the file is changed::

  $ echo hello >> /tmp/webshop/backend/postgres1/etc/postgres/8.4/pg_hba.conf
  $ poni audit -v --path-prefix=/tmp
  manager	WARNING	 DIFFERS webshop/backend/postgres1: /tmp/webshop/backend/postgres1/etc/postgres/8.4/pg_hba.conf

The difference to the proper contents can be viewed by adding the ``--diff`` argument::

  $ poni audit -v --path-prefix=/tmp --diff
  manager	WARNING	 DIFFERS webshop/backend/postgres1: /tmp/webshop/backend/postgres1/etc/postgres/8.4/pg_hba.conf
  --- config
  +++ active 2011-03-02 19:38:41
  @@ -2,3 +2,4 @@
   # TYPE  DATABASE        USER            ADDRESS                 METHOD
   local   all             all                                     trust

  +hello

To repair the file, simply run the ``deploy`` command again::

  $ poni deploy postgres1 --path-prefix=/tmp
  manager	INFO	   WROTE webshop/backend/postgres1: /tmp/webshop/backend/postgres1/etc/postgres/8.4/pg_hba.conf
  $ poni audit -v --path-prefix=/tmp --diff
  manager	INFO	      OK webshop/backend/postgres1: /tmp/webshop/backend/postgres1/etc/postgres/8.4/pg_hba.conf
