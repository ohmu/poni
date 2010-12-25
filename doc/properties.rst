.. _propref:

System and Node Property Reference
==================================

Properties Controlled by Poni
-----------------------------
The following properties are automatically maintained by Poni:

.. list-table::
   :widths: 10 30 8 30
   :header-rows: 1

   * - Property
     - Description
     - Data Type
     - Example
   * - ``depth``
     - How many levels deep the node (or system) is in the hierarchy
     - integer
     - ``1`` (means: root-level)
   * - ``index``
     - Location  of the node/system in relation to its siblings in the same
       system
     - integer
     - ``0`` (means: first node)

Generic Properties
------------------

.. list-table::
   :widths: 10 30 8 30
   :header-rows: 1

   * - Property
     - Description
     - Data Type
     - Example
   * - ``host``
     - Host network address (used with SSH-based access)
     - string
     - ``server01.company.com``
   * - ``user``
     - Username for accessing the host (used with SSH-based access)
     - string
     - ``root``
   * - ``ssh-key``
     - Filename of the SSH key used to access the host as ``user``
     - string
     - ``id_rsa``
   * - ``parent``
     - Full name of the parent node (if defined), set automatically when node
       is created with ``poni add-node CHILD -i PARENT``
     - string
     - ``some/other/node``
   * - ``verify``
     - Is verification enabled for this node/system and all of its
       sub-systems? Set to ``false`` for e.g. template nodes. **NOTE:**
       Affects all sub-systems and their nodes, too.
     - boolean
     - ``true`` (verification is enabled) or ``false`` (verification is
       disabled)
   * - ``deploy``
     - Node access method. Default is ``ssh`` if not defined with this
       property. **NOTE:** Affects all sub-systems and their nodes, too.
     - string
     - ``ssh`` or ``local``

Amazon EC2 Properties
---------------------
.. list-table::
   :widths: 15 30 3 8 30
   :header-rows: 1

   * - Property
     - Description
     - Required
     - Data Type
     - Example
   * - ``cloud.provider``
     - Selects the cloud provider, must be ``aws-ec2``
     - **YES**
     - string
     - ``aws-ec2``
   * - ``cloud.image``
     - The "AMI" code of the VM image
     - **YES**
     - string
     - ``ami-daf615b3``
   * - ``cloud.kernel``
     - The "AKI" code of the kernel
     - NO
     - string
     - ``aki-6eaa4907``
   * - ``cloud.ramdisk``
     - The "ARI" code of the ramdisk
     - NO
     - string
     - ``ari-42b95a2b``
   * - ``cloud.region``
     - AWS EC2 data-center
     - **YES**
     - string
     - one of ``us-west-1``, ``us-east-1``, ``eu-west-1`` or ``ap-southeast-1``
   * - ``cloud.type``
     - Instance type
     - NO
     - string
     - ``m1.small``, ``m2.xlarge``, etc.
   * - ``cloud.key-pair``
     - Name of the EC2 data-center specific key-pair to use **without** the
       ``.pem`` suffix
     - **YES**
     - string
     - ``my-key-pair`` (in case the file you have is ``my-key-pair.pem``)
   * - ``instance``
     - Poni updates the id of the instance here once it has been started
     - n/a
     - string
     - ``i-4692cd2b``

.. note::
  Many EC2 instance properties cannot be controlled yet, for example: security
  groups, user data, addressing types, placement groups, monitoring, subnets
  or block devices.
