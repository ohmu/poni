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
   * - ``ssh-port``
     - SSH server port number. If not set, a default value from the
       environment variable ``PONI_SSH_PORT`` is used. If that is not set,
       then the standard port ``22`` is used.
     - string
     - ``8022``
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
   * - ``template``
     - Indicates a system or node only containing templates. Control commands
       are not run under template nodes and implies ``verify=false``.
     - boolean
     - ``true`` (system/node contains only templates) or ``false`` (regular
       system/node, default)
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
   * - ``cloud.key_pair``
     - Name of the EC2 data-center specific key-pair to use **without** the
       ``.pem`` suffix
     - **YES**
     - string
     - ``my-key-pair`` (in case the file you have is ``my-key-pair.pem``)
   * - ``cloud.instance``
     - Poni updates the id of the instance here once it has been started
     - n/a
     - string
     - ``i-4692cd2b``
   * - ``cloud.vm_name``
     - User-friendly name for the VM, visible in the EC2 console.
     - **YES**
     - string
     - ``cloud-server-01``
   * - ``cloud.placement``
     - The availability zone in which to launch the instance.
     - NO
     - string
     - ``us-east-1c``
   * - ``cloud.placement_group``
     - Name of the placement group in which the instance will be launched.
     - NO
     - string
     - ``my-group``
   * - ``cloud.billing``
     - Instance billing type
     - NO
     - string
     - ``on-demand`` (default) or ``spot``
   * - ``cloud.spot.max_price``
     - Spot instance maximum price, required if ``cloud.billing`` is set to ``spot``.
     - NO
     - float
     - ``0.123``
   * - ``cloud.hardware``
     - Extra "hardware" to attach to the instance. (See description below)
     - NO
     - dict
     - ``{"disk0": {"size": 2048, "device": "/dev/sdh"}``
   * - ``disable_api_termination``
     - If True, the instances will be locked and will not be able to be terminated via the API.
     - NO
     - bool
     - ``False`` (default) or ``True``
   * - ``monitoring_enabled``
     - Enable CloudWatch monitoring on the instance.
     - NO
     - bool
     - ``False`` (default) or ``True``
   * - ``subnet``
     - The subnet ID or name within which to launch the instances for VPC. The name is in subnet
       object's tags with the key 'Name'.
     - NO
     - str
     - ``<subnet id>``, ``My subnet X``
   * - ``private_ip_address``
     - If you’re using VPC, you can optionally use this parameter to assign the
       instance a specific available IP address from the subnet.
     - NO
     - str
     - ``10.0.0.25``
   * - ``tenancy``
     - The tenancy of the instance you want to launch. An instance with a
       tenancy of ‘dedicated’ runs on single-tenant hardware and can only be
       launched into a VPC. Valid values are: “default” or “dedicated”.
       NOTE: To use dedicated tenancy you MUST specify a VPC subnet-ID as well.
     - NO
     - str
     - ``default``, ``dedicated``
   * - ``instance_profile_name``
     - IAM instance profile name.
     - NO
     - str
     - ``<profile name>``
   * - ``extra_tags``
     - Extra tag names and corresponding values used to tag the created VM instances.
       Can be used to maintain extra book-keeping of e.g. owners of the VMs in a
       shared environment. Note that each key and value are required to be strings.
     - NO
     - dict
     - ``'cloud.extra_tags:-json={"cost_centre": "12345", "owner": "John Doe"}'``
   * - ``init_timeout``
     - Maximum time to wait until instance reaches healthy running status after
       creation. If not specified the value from the environment variable
       ``PONI_AWS_INIT_TIMEOUT`` is used. If the environment variable is not
       defined, then a default of ``300.0`` seconds is used.
     - NO
     - float or int
     - ``600.0``
   * - ``check_health``
     - Control usage of "instance" and "system" health checks during ``cloud init``.
       If ``True`` (default), wait until both health checks return "ok". Otherwise
       proceed immediately without checking instance health. Leaving this enabled
       will result in a somewhat slower instance creation as the health check
       results are not immediately available after the instance is "running".
     - NO
     - float
     - ``True`` or ``False``

.. note::
  Many EC2 instance properties cannot be controlled yet, for example: user data,
  addressing types or monitoring.


Extra Hardware
~~~~~~~~~~~~~~
The ``cloud.hardware`` property can be used to define additional EBS volumes to
be created and automatically attached to the instance. The value needs to be a
``dict`` and can be set as follows::

  poni set some/server 'cloud.hardware:-json={"disk0": {"size": 2048, "device": "/dev/sdh"}'

The keys in the dict (or JSON object...) define the type of the hardware
resource, currently ``disk0..disk9`` are supported. Each disk definition
corresponds to one EBS volume and one device path within the instance.

The value of each ``diskN`` is another dict/JSON object, definiting the
properties of the disk:

.. list-table::
   :widths: 15 30 3 8 30
   :header-rows: 1

   * - Property
     - Description
     - Required
     - Data Type
     - Example
   * - ``size``
     - Size in megabytes, must be at least 1024 MB.
     - **YES**
     - int
     - ``8192`` (8 GB)
   * - ``device``
     - Device path within the instance where the volume will be available.
     - **YES**
     - string
     - ``/dev/sdh``
   * - ``delete_on_termination``
     - If set to false, the EBS volume will remain after the instance gets terminated.
     - NO
     - bool
     - ``true`` (default), ``false``
