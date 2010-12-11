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
     - dict
     - ``$node.private.dns``
   * - ``settings``
     - Config settings (with all settings layers applied)
     - dict
     - ``$settings.my_server.http_port``
   * - ``s``
     - **deprecated** Use ``settings`` instead
     -
     -
   * - ``system``
     - System properties of the current node's system
     - dict
     - ``$system.sub_count``
   * - ``config``
     - Config properties
     - dict
     - ``$system.get("parent", "orphan!")``
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
   :rtype: generator object returning node objects

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

.. function:: get_node(TODO)

   TODO: desc

.. function:: get_system(TODO)

   TODO: desc

.. function:: get_config(TODO)

   TODO: desc

.. function:: find_config(TODO)

   TODO: desc

.. function:: edge(TODO)

   TODO: desc

.. function:: bucket(TODO)

   TODO: desc
