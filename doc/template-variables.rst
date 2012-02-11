================================
Template Variables and Functions
================================

Variables
---------
The following variables are accessible from templates:

.. list-table::
   :widths: 20 30 20 30
   :header-rows: 1

   * - Variable
     - Description
     - Data Type
     - Example Usage
   * - ``node``
     - Node properties
     - ``poni.core.Node``
     - ``$node.private.dns``
   * - ``settings``
     - Config settings (with all settings layers applied), shortcut to ``$config.settings``
     - dict
     - ``$settings.my_server.http_port``
   * - ``s``
     - **deprecated** Use ``settings`` instead
     -
     -
   * - ``system``
     - System properties of the current node's system
     - ``poni.core.System``
     - ``$system.sub_count``
   * - ``config``
     - Config properties
     - ``poni.core.Config``
     - ``$config.name``, ``$config.settings``
   * - ``plugin``
     - Current config's plug-in object. Allows e.g. calling custom methods
       defined in your ``plugin.py`` file.
     - ``poni.core.PlugIn``
     - ``$plugin.my_custom_method($node, "hello")``

Functions
---------
The following functions are accessible from templates:

.. function:: find(pattern, nodes=True, systems=False, full_match=False)

   Find nodes and/or systems matching the given search pattern.

   :param pattern: Regular expression node path pattern
   :param nodes: Returns nodes if True
   :param systems: Returns systems if True
   :param full_match: Require full regexp match instead of default sub-string
                      match
   :rtype: generator object returning Node objects

   Example usage::

     #for $node in $find("webshop/frontend")
       $node.name has address $node.host
     #end for

.. function:: find_config(pattern, all_configs=False, full_match=False)

   Find configs matching given pattern.

   A double-backslash combination in the pattern signifies "anything", i.e.
   ``//foo`` will find all ``foo`` configs in the entire system and
   ``bar//baz`` will find all ``baz`` configs under the ``bar`` system.

   :param pattern: Regular expression config path pattern.
   :param all_configs: Returns also inherited configs if True
   :param full_match: Require full regexp match instead of default sub-string
                      match
   :rtype: generator object returning ``(node, config)`` pairs

   Example usage::

     # find all "http-server" configs under the entire "webshop" system:
     #for $node, $conf in $find_config("webshop//http-server", all_configs=True)
       $node.name has $conf.name at port $conf.settings.server_port
     #end for

.. function:: get_node(pattern)

   Return exactly one node that matches the pattern. An error is raise if
   zero or more than one nodes match the pattern.

   :param pattern: Regular expression node path pattern.
   :rtype: Node object

.. function:: get_system(pattern)

   Return exactly one system that matches the pattern. An error is raise if
   zero or more than one systems match the pattern.

   :param pattern: Regular expression system path pattern.
   :rtype: System object

.. function:: get_config(pattern)

   Return exactly one node and one config that matches the pattern. An error
   is raise if zero or more than one configs match the pattern.

   :param pattern: Regular expression system/node/config path pattern.
   :rtype: a single tuple of (Node, Config)

.. function:: edge(bucket_name, dest_node, dest_config, **kwargs)

   Add a directed graph edge as a ``dict`` object into a bucket. This can be
   used to, for example, automatically collect information about network
   connections between nodes.

   :param bucket_name: Bucket name
   :type bucket_name: string
   :param dest_node: Edge destination node
   :type dest_node: ``poni.core.Node``
   :param dest_config: Edge destination config
   :type dest_config: ``poni.core.Config``
   :param kwargs: Extra information to store in the ``dict`` object

   Example usage::

     #for $db_node, $db_config in $find_config("webshop//pg84")
       $edge("tcp", $db_node, $db_config, protocol="sql", port=$db_config.settings.db_server_port)#slurp
     #end for

.. function:: bucket(bucket_name)

   Return a bucket object for accessing dynamically collected data during
   the template rendering process.

   :param bucket_name: Bucket name
   :type bucket_name: string
   :rtype: ``list`` object

   **NOTE:** Accessing buckets from templates should be done only after all
   other templates are rendered so that all dynamic data is collected. This
   can be achieved by giving the extra ``report=True`` argument to the
   ``poni.core.PlugIn`` ``add_file()`` call.

   Example usage::

     #for $item in $bucket("tcp")
     Node $item.source_node.name config $item.source_config.name connects to:
       $item.dest_node:$item.port for some $item.protocol action...
     #end for

   Registering the template to be processed after all regular templates::

     class PlugIn(config.PlugIn):
         def add_actions(self):
             self.add_file("node-report.txt", dest_path="/tmp/", report=True)
