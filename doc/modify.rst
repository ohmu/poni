=================================
Modifying Properties and Settings
=================================

.. include:: definitions.rst

Overview
========
Although these examples use the ``set`` command, the functionality is mostly the same for
the ``settings set`` command and for the extra ``variable`` arguments of the ``script`` 
command.

Properties vs. Settings
=======================
Each node and system has their own set of "properties". Some of the properties have 
special behavior as described in the :ref:`propref`. 

Properties are stored internally in the Poni repository as JSON_ and all data-types and
structures supported by JSON_ can be used in Poni. Hierarchies of properties can be 
created and accessed with the dot-syntax, e.g. 
``poni set somenode server.http.port:int=80`` or ``$node.server.http.port`` in Cheetah_ 
templates.

The repository JSON storage format is kept sorted by key and pretty-printed for 
readability especially when using a version control system to store the repository::

  $ poni add-node example
  $ poni set example server.http.port:int=80 server.http.interface=127.0.0.1 
  $ cat ~/.poni/default/system/example/node.json 
  {
      "host": "", 
      "server": {
          "http": {
              "interface": "127.0.0.1", 
              "port": 80
          }
      }
  }

Example version control diff::

  $ poni vc checkpoint baseline
  $ poni set example server.http.port:int=8080
  $ poni vc diff
  Changes:
  diff --git a/system/example/node.json b/system/example/node.json
  index ae0a8f4..4e86c5d 100644
  --- a/system/example/node.json
  +++ b/system/example/node.json
  @@ -3,7 +3,7 @@
       "server": {
           "http": {
               "interface": "127.0.0.1", 
  -            "port": 80
  +            "port": 8080
           }
       }
   } 
  \ No newline at end of file

Properties are for storing node/system-specific information that is not e.g. inherited 
automatically from parent-nodes. However, when adding nodes with the ``add-node`` command,
their properties can be **copied** (once) from the parent node with the ``--copy-props`` 
switch.

.. note:: Properties currently do not support explicit typing or validation schemas: any
          data-types can be used, but they are not actively verified.

Settings are config-specific repositories and share the same structure and storage format
with properties. However, config settings have a bit more features, namely inheritance
and type validation.

Settings Type Validation
------------------------
TODO

Settings Inheritance
--------------------
TODO

Setting Basic Node and System String Properties
===============================================
It is often necessary to set some basic node properties, such as the hostname or the 
IP-address::

  $ poni list -p
      node  webshop/frontend/server1
      prop      depth:3, host:'', index:0
      node  webshop/frontend/server2
      prop      depth:3, host:'', index:1
  $ poni set -v server1 host=www.google.com
  root	INFO	webshop/frontend/server1: set host=u'www.google.com' (was u'')
  $ poni set -v server2 host=www.amazon.com
  root	INFO	webshop/frontend/server2: set host=u'www.amazon.com' (was u'')

In the above example setting string properties is done by using the form ``name=value``. 
The ``-v`` or ``--verbose`` flag enables every change made to be printed out.

.. note:: Internally string properties are stored in Unicode form and the ``u`` before 
          the values in the above output indicate this.

Setting Integer, Float, Boolean Data-types
==========================================
Other data-types can be specified by adding a colon and the type after the property name::

  $ poni set -v server1 foo:int=123 bar:float=456.7 baz:bool=true
  root	INFO	webshop/frontend/server1: set baz=True (was None)
  root	INFO	webshop/frontend/server1: set foo=123 (was None)
  root	INFO	webshop/frontend/server1: set bar=456.69999999999999 (was None)

Integer values can be specified in binary, octal, decimal or hexdecimal format::

  $ poni set -v server2 a:int=0b1010 b:int=0o644 c:int=0xff
  root	INFO	webshop/frontend/server2: set a=10 (was None)
  root	INFO	webshop/frontend/server2: set c=255 (was None)
  root	INFO	webshop/frontend/server2: set b=420 (was None)

Integer or float values can optionally specify SI (base-10) or IEEE-1541 (base-2) 
multipliers::

  $ poni set -v server2 max_mem:int=64Mi disk_space:int=100Gi network_speed:int=100M
  root	INFO	webshop/frontend/server2: set disk_space=107374182400 (was None)
  root	INFO	webshop/frontend/server2: set network_speed=100000000 (was None)
  root	INFO	webshop/frontend/server2: set max_mem=67108864 (was None)

Null values
===========
A null value (``None`` in Python) can be set with ``null`` as the data type::

  $ poni set -v server2 nothing:null	INFO	webshop/frontend/server2: set nothing=None (no change)

Eval expressions
================
Simple Python-expressions can be evaluated using the ``eval`` conversion::

  $ poni set -v server2 meaning:eval=21*6/3
  root	INFO	webshop/frontend/server2: set meaning=42 (was None)

  $ poni set -v server2 'msglen:eval=len("hello, world")'
  root	INFO	webshop/frontend/server2: set msglen=12 (was None)

Accessing Environment Variables
===============================
Enviroment variables can be stored as properties using the ``env`` conversion::

  $ poni set server2 -v term:env=TERM shell:env=SHELL
  root	INFO	webshop/frontend/server2: set term=u'xterm-color' (was None)
  root	INFO	webshop/frontend/server2: set shell=u'/bin/bash' (was None)

Optionally you can use following syntax

  $ poni set server2 -v must_be_set:env=MUST optional1:env=OPT1| optional2:env=OPT2|default_value

In this case poni will complain if MUST environment variable is not set. For optional1 value will
be either env value OPT1 or '' if OPT1 is unset. For OPT2 value optional2 is either
environmental value or string 'default_value' if OPT2 is unset.

Resolving IP Addresses
======================
Resolving DNS names to IPv4 or IPv6 addresses::

  $ poni set -v server2 address1:ipv4=www.funet.fi address2:ipv6=www.funet.fi
  root	INFO	webshop/frontend/server2: set address1=u'81.90.77.32' (was None)
  root	INFO	webshop/frontend/server2: set address2=u'2a00:16a0:0:100::21:3' (was None)

.. note:: Currently only the first available IP address is returned. If there are more
          than one IPs, the rest are just discarded. Also note that resolving the address
          is done only once (during the ``set`` command) and not updated automatically.

Two-way Conversions
===================
Many conversions can be done in two ways: "to format X" (encoding) and "from format X"
(decoding). Let's use hex encoding strings as the example::

  $ poni set server2 -v message:hex=hello 
  root	INFO	webshop/frontend/server2: set message='68656c6c6f' (was None)
 
I the above example the default direction, which is to encode, was used and "hello" was
converted to its hexadecimal representation. In order to specify decoding instead of
encoding, a minus-sign is added before the conversion name::

  $ poni set server2 -v message:-hex=68656c6c6f
  root	INFO	webshop/frontend/server2: set message='hello' (was u'68656c6c6f')

A plus-sign can be added in a similar fashion to explicitly define that encoding is 
requested, but it is redundant as the default is always to encode.

Python standard codec names (see 
http://docs.python.org/library/codecs.html#standard-encodings) can be used in 
conversions, for example::

  $ poni set server2 -v secret:rot13=confidential example:base64=hello123 
  root	INFO	webshop/frontend/server2: set secret='pbasvqragvny' (was None)
  root	INFO	webshop/frontend/server2: set example='aGVsbG8xMjM=\n' (was None)

Character Set Conversions
=========================
TODO

Accessing Node Properties
=========================
Referencing node properties (``set`` command) or config properties (``set`` or 
``settings set`` commands) is available thru the ``prop`` directive. To copy an existing
property::

  $ poni set -v server2 host2:prop=node.host
  root	INFO	webshop/frontend/server2: set host2=u'www.amazon.com' (was None)

Chaining conversions
====================
Multiple conversions can be chained together by adding more conversion separated by
colons. For example, updating the ``private.ip`` node property by resolving the IP 
address of each host:: 

  $ poni add-node linux/debian
  $ poni add-node linux/ubuntu
  $ poni set linux/debian host=www.debian.org
  $ poni set linux/ubuntu host=www.ubuntu.org
  $ poni set -v linux/ private.ip:prop:ipv4=node.host
  root	INFO	linux/debian: set private.ip=u'213.129.232.18' (was None)
  root	INFO	linux/ubuntu: set private.ip=u'147.83.195.55' (was None)

The funky part is the ``private.ip:prop:ipv4=node.host`` property definition. Let's break
it into parts: 

* ``private.ip`` defines the property we are overwriting
* There are two conversions: ``prop`` and ``ipv4`` (in that order!)
* The starting value is a string containing the characters: ``node.host``

Here's how the whole thing gets processed for the ``linux/debian`` node:

#. The string value ``node.host`` is fed to the ``prop`` conversion, which looks up the 
   ``host`` property of the ``node`` object, which results in the value 
   ``www.debian.org``.
#. The string value ``www.debian.org`` is given to the ``ipv4`` conversion, which then
   tries to resolve the IP address behind it. The result is ``213.129.232.18``.
#. Finally, the value ``213.129.232.18`` is stored into the ``private.ip`` node property.

Encoding and Decoding JSON 
==========================
Data can be converted to and front JSON using the ``json`` conversion. For example, to
decode a JSON input string and store the resulting object we can do something like this::

  $ poni set server2 -v 'json_example:-json=[1, 2.3, "hello"]'
  root	INFO	webshop/frontend/server2: set json_example=[1, 2.2999999999999998, u'hello'] (was None)

Note the minus-sign before ``json``, indicating the decoding **from JSON** is requested.
Encoding the sample input string **to JSON** (plus-sign) results in just wrapping the 
input string into a JSON string by adding one more level of quotes::

  $ poni set server2 -v 'json_example2:+json=[1, 2.3, "hello"]'
  root	INFO	webshop/frontend/server2: set json_example2='"[1, 2.3, \\"hello\\"]"' (was None)

Creating and Setting UUIDs
==========================
Conversion ``uuid4`` can be used to create new totally random UUID_::

  $ poni set server -v nodeid:uuid4
  root	INFO	webshop/frontend/server1: set nodeid=u'38c7363d-9fec-49d0-a1a0-913715caa04b' (was None)
  root	INFO	webshop/frontend/server2: set nodeid=u'34075320-2b84-412d-8034-f45017edf7f4' (was None)

Converting a 16-byte string into UUID_ format::

  $ poni set server1 -v sampleid:uuid=0123456789abcdef
  root	INFO	webshop/frontend/server1: set sampleid=u'30313233-3435-3637-3839-616263646566' (was None)

