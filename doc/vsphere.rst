Provisioning with Vmware vSphere
================================

Poni can provision machines through Vmware vSphere automatically using the pyvsphere wrapper.


Pre-requisites
--------------
* A working installation of vSphere
* A vSphere user with enough privileges to administer virtual machines
* A virtual machine image as a base for cloning
* pyvsphere: Python interface to vSphere
* suds: SOAP library for Python, required by pyvsphere


Basic Setup
-----------

For the vSphere module to work user credentials and the vSphere server URL must
be provided. These can be placed into the properties ``cloud.url``, ``cloud.username``,
``cloud.password`` or the environment variable counterparts ``VI_URL``, ``VI_USERNAME``
``VI_PASSWORD``. In case any of these items is specified in both places, the environment
variable takes precedence.


Configuring Nodes
-----------------
At minimum, the following node properties need to be set:

  ``cloud.provider``
    Must be ``vsphere``.

  ``cloud.vm_name``
    Name of the VM, which needs to be unique in vSphere.
    This name will also serve as the cloud instance ID.

  ``cloud.base_vm_name``
    Name of the image to clone the machines from.

In case of a more complex setup, for example multiple clusters in vSphere,
more properties might need to be set. See the `Virtual Machine Placement`_ section
for more details.

Creating a repository and a node from scratch::

  $ poni init
  $ poni add-node drumbo1
  $ poni add-node drumbo2
  $ poni set drumbo cloud.provider=vsphere cloud.base_vm_name='My Base VM' cloud.cluster='My Cluster'
  $ poni set drumbo1 cloud.vm_name=drumbo1
  $ poni set drumbo2 cloud.vm_name=drumbo2

In order to see the cloud properties you can use ``list -o``::

  $ poni list -o
    node  drumbo1
   cloud      base_vm_name:'My Base VM', provider:'vsphere', vm_name:'drumbo1'
    node  drumbo2
   cloud      base_vm_name:'My Base VM', provider:'vsphere', vm_name:'drumbo2'

Now the nodes are ready to be started.


Starting Nodes
--------------
Node instances are created with the ``init`` cloud command::

  $ poni cloud init drumbo --wait

  poni    INFO    drumbo1: initialized: vm_name=u'drumbo1', cluster=u'My Cluster', instance=u'drumbo1', base_vm_name=u'My Base VM', provider=u'vsphere'
  poni    INFO    drumbo2: initialized: vm_name=u'drumbo2', cluster=u'My Cluster', instance=u'drumbo2', base_vm_name=u'My Base VM', provider=u'vsphere'
  pyvsphere.vmops DEBUG   Datastores for VM My Base VM: VI.1.10,VI.1.09,VI.1.07,VI.1.08,VI.1.06,VI.1.05,VI.1.03,VI.1.04,VI.1.11,VI.1.12
  pyvsphere.vmops DEBUG   CLONE(drumbo1) CLONE STARTING
  pyvsphere.vmops DEBUG   CLONE(drumbo2) CLONE STARTING
  poni.vsphere    INFO    0 instances 'running', waiting...
  poni.vsphere    INFO    0 instances 'running', waiting...
  poni.vsphere    INFO    0 instances 'running', waiting...
  poni.vsphere    INFO    0 instances 'running', waiting...
  pyvsphere.vmops DEBUG   CLONE(drumbo1) CLONE DONE
  pyvsphere.vmops DEBUG   CLONE(drumbo1) POWERON STARTING
  pyvsphere.vmops DEBUG   CLONE(drumbo1) POWERON DONE
  pyvsphere.vmops DEBUG   CLONE(drumbo1) WAITING FOR IP
  pyvsphere.vmops DEBUG   CLONE(drumbo1) GOT IP: 10.133.59.78
  pyvsphere.vmops DEBUG   CLONE(drumbo1) SNAPSHOT STARTING
  pyvsphere.vmops DEBUG   CLONE(drumbo2) CLONE DONE
  pyvsphere.vmops DEBUG   CLONE(drumbo2) POWERON STARTING
  pyvsphere.vmops DEBUG   CLONE(drumbo2) POWERON DONE
  pyvsphere.vmops DEBUG   CLONE(drumbo2) WAITING FOR IP
  pyvsphere.vmops DEBUG   CLONE(drumbo1) SNAPSHOT DONE
  pyvsphere.vmops DEBUG   CLONE(drumbo2) GOT IP: 10.133.59.79
  pyvsphere.vmops DEBUG   CLONE(drumbo2) SNAPSHOT STARTING
  pyvsphere.vmops DEBUG   CLONE(drumbo2) SNAPSHOT DONE
  poni    INFO    drumbo1: updated: host=10.133.59.78 (from u''), private={'ip': 10.133.59.78, 'dns': 10.133.59.78} (from None)
  poni    INFO    drumbo2: updated: host=10.133.59.79 (from u''), private={'ip': 10.133.59.79, 'dns': 10.133.59.79} (from None)

Creating a node from scratch involves a clone, power on and snapshot cycle, as illustrated by
the previous example output. In case the node needs to be reused later the VM can be started
by reverting to the clean snapshot called 'pristine', which is usually faster than cloning.

Since node initialization process involves multiple steps, coordinated by poni, the --wait
option always needs to be specified with coud init.

Once all instances are running, Poni refreshes the updated nodes properties into the Poni
repository.

Now the cloud properties include the ``instance`` value::

  $ poni list -o
    node  drumbo1
   cloud      base_vm_name:'My Base VM', cluster:'My Cluster', instance:'drumbo1', provider:'vsphere', vm_name:'drumbo1'
    node  drumbo2
   cloud      base_vm_name:'My Base VM', cluster:'My Cluster', instance:'drumbo2', provider:'vsphere', vm_name:'drumbo2'

Also the node address information is updated to the node properties::

  $ poni list -p
    node  drumbo1
    prop      depth:1, host:'10.133.59.78', index:0, private:{dns:'10.133.59.78', ip:'10.133.59.78'}
    node  drumbo2
    prop      depth:1, host:'10.133.59.79', index:1, private:{dns:'10.133.59.79', ip:'10.133.59.79'}

The following properties are updated:

  ``host``
    Full public internet DNS name
  ``private.dns``
    Full network hostname
  ``private.ip``
    Network IP-address


Checking Instance Status
------------------------
The ``list -q`` queries each cloud instances' status and shows it in the output::

  $ poni list -q
    node  drumbo1
  status      VM_RUNNING
    node  drumbo2
  status      VM_RUNNING


Snapshot Management
-------------------

The vSphere provider adds three cloud commands to manage VM snapshots through
poni: ``create-snapshot``, ``revert-to-snapshot`` and ``remove-snapshot``. An example
session could go as follows::

  $ poni cloud create-snapshot foo drumbo
  pyvsphere.vmops DEBUG   CREATE-SNAPSHOT(drumbo1) STARTING
  pyvsphere.vmops DEBUG   CREATE-SNAPSHOT(drumbo2) STARTING
  pyvsphere.vmops DEBUG   CREATE-SNAPSHOT(drumbo1) DONE
  pyvsphere.vmops DEBUG   CREATE-SNAPSHOT(drumbo2) DONE

  $ poni cloud revert-to-snapshot pristine drumbo
  pyvsphere.vmops DEBUG   REVERT(drumbo1) STARTING
  pyvsphere.vmops DEBUG   REVERT(drumbo2) STARTING
  pyvsphere.vmops DEBUG   REVERT(drumbo2) DONE
  pyvsphere.vmops DEBUG   REVERT(drumbo1) DONE

  $ poni cloud remove-snapshot foo drumbo
  pyvsphere.vmops DEBUG   REMOVE-SNAPSHOT(drumbo1) STARTING
  pyvsphere.vmops DEBUG   REMOVE-SNAPSHOT(drumbo2) STARTING
  pyvsphere.vmops DEBUG   REMOVE-SNAPSHOT(drumbo1) DONE
  pyvsphere.vmops DEBUG   REMOVE-SNAPSHOT(drumbo2) DONE

``create-snapshot`` takes two arguments, ``--description`` to attach a short text
description to the snapshot and ``--memory`` to enable snapshotting of VM memory.
The other two commands only take the snapshot name and poni targets as arguments.


Terminating Instances
---------------------
To get rid of instances use the ``cloud terminate`` command::

  $ poni cloud terminate drumbo
  pyvsphere.vmops DEBUG   DELETE(drumbo1) POWEROFF STARTING
  poni.vsphere    INFO    [0/1] instances being terminated, waiting...
  pyvsphere.vmops DEBUG   DELETE(drumbo1) POWEROFF DONE
  pyvsphere.vmops DEBUG   DELETE(drumbo1) DELETE STARTING
  poni.vsphere    INFO    [0/1] instances being terminated, waiting...
  poni.vsphere    INFO    [0/1] instances being terminated, waiting...
  pyvsphere.vmops DEBUG   DELETE(drumbo1) DELETE DONE
  poni.vsphere    INFO    [1/1] instances being terminated, waiting...
  poni    INFO    terminated: drumbo1
  pyvsphere.vmops DEBUG   DELETE(drumbo2) POWEROFF STARTING
  poni.vsphere    INFO    [0/1] instances being terminated, waiting...
  pyvsphere.vmops DEBUG   DELETE(drumbo2) POWEROFF DONE
  pyvsphere.vmops DEBUG   DELETE(drumbo2) DELETE STARTING
  poni.vsphere    INFO    [0/1] instances being terminated, waiting...
  pyvsphere.vmops DEBUG   DELETE(drumbo2) DELETE DONE
  poni.vsphere    INFO    [1/1] instances being terminated, waiting...
  poni    INFO    terminated: drumbo2
  poni    INFO    2 instances terminated


Virtual Machine Placement
-------------------------

cloud_vsphere makes an attempt to auto-detect the resource pool for the new VMs.
In case there is only a single cluster in vSphere it will pick the root pool of
that cluster, otherwise it will fail with a similar error message, indicating that
the cloud.cluster property must be specified::

  poni.vsphere    ERROR   drumbo1 failed: root resource pool could not be determined unambiguously, specify the 'cluster' parameter

Datastore placement is controlled by a number of cloud properties. If none are
specified, one will be randomly picked from all datastores available to the
user. The list of datastores can be limited first by specifying the ``cloud.cluster``
to include on the ones available under that. Also, ``cloud.datastore_filter`` can
require a substring to be present in the candidate names. These two can be used
in any combination.

Once a list of candidate datastores is obtained, the final datastore will be
selected by the ``random`` or ``most-space`` strategy as specified in ``cloud.placement``,
which defaults to ``random``.

In any case, only datastores with enough freee space to hold the VM will be considered.


Hardware Configuration
----------------------

It is possible to instruct the vSphere cloud provider to alter the configuration
of the newly created hosts. For example the number of attached virtual CPUs or
the amount of memory can be changed by setting the ``cloud.hardware.cpus`` and
``cloud.hardware.ram`` properties.

New disks and network interfaces can be added, up to 10, as follows by setting
the ``cloud.hardware.diskX`` and ``cloud.hardware.nicX`` properties where X can
be from 0 to 9 and will be processed in numeric order.

All the available properties for each harware type are documented in the
`Cloud Property Reference`_ section.


Cloud Property Reference
------------------------

  ``cloud.url``
    URL of the vSphere server in the format ``https://<your_server>/sdk``

  ``cloud.username``
    Username the vSphere server

  ``cloud.password``
    Password for the vSphere user

  ``cloud.provider``
    Must be ``vsphere``.

  ``cloud.base_vm_name``
    Name of the image to clone the machines from

  ``cloud.vm_name``
    Unique name for the VM. Provides the VM with a friendly name visible in
    the EC2 console. This name will also serve as the cloud instance ID.

  ``cloud.cluster``
    Name of ComputeResource where to find resource pools and datastores.

  ``cloud.resource_pool``
    Resource pool to place the VM.

  ``cloud.datastore``
    Name of datastore to place the VM.

  ``cloud.datastore_filter``
    Pattern to limit the datastore list. The specified string is used as a simple
    substring pattern which needs to be present in all the datastore names to be
    considered.

  ``cloud.placement``
    Strategy to pick a datastore from the available list. Can be either ``random`` or
    ``most-space``.

  ``cloud.folder``
    Name of folder to place the VM. The format is ``Data Center/vm/Any/Folder/Name``.
    Please note the ``/vm/`` in middle which needs to be present, even though it is
    not shown in the vSphere client.

  ``cloud.hardware.cpus``
    Sets the number of CPUs to be attached to the VM.

  ``cloud.hardware.ram``
    Sets the amount of available RAM for the VM in megabytes.

  ``cloud.hardware.disk<X>.size``
    Size of the disk in kilobytes.

  ``cloud.hardware.disk<X>.provisioning``
    ``thin`` or ``thick`` provisioning for the disk.

  ``cloud.hardware.disk<X>.mode``
    Disk mode, one of ``persistent``, ``independent_persistent``, ``independent_nonpersistent``,
    ``nonpersistent``, ``undoable`` or ``append``. See the vSphere documentation for
    details.

  ``cloud.hardware.nic<X>.network``
    Name of virtual network to connect the interface to.

  ``cloud.hardware.nic<X>.nic_type``
    Type of network interface, can be one of ``e1000``, ``pcnet32``, ``vmxnet2`` or
    ``vmxnet3``. The default is ``vmxnet3``.

  ``cloud.network.gateway``
    Static gateway address for the node.

  ``cloud.network.username``
    Username with enough privileges on the node to set IP configuration, typically ``root``.
    The network configuration mechanism uses VM guest operations to log into the host
    and execute the appropriate commands.

  ``cloud.network.password``
    Password for the admin user.

  ``cloud.network.<interface name>.address``
    Static IPV4 address of the network interface.

  ``cloud.network.<interface name>.netmask``
    Static IPV4 netmask of the network interface.


.. include:: definitions.rst
