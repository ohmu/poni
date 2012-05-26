Cloud Provisioning with Amazon EC2
==================================
Poni can manage provisioning your VMs from Amazon's EC2 for you. There is a little
setup involved, which is covered in the next section.

Pre-requisites
--------------
* Basic EC2 knowledge (AMIs, key-pairs, security groups, etc.)
* `Amazon EC2`_ account (amazingly)
* Key-pair for each of the data-centers (e.g. ``us-west-1``, ``eu-west-1``, etc.) you
  will be using
* EC2 access key and secret key

Your EC2 credentials need to be stored in the following environment variables::

  export AWS_ACCESS_KEY_ID=<your aws access key>
  export AWS_SECRET_ACCESS_KEY=<your aws secret access key>

The key-pairs need to be copied to::

  $HOME/.ssh/<aws-key-pair-name>.pem

Limitations:

* Currently the "default" security group is applied to all VMs, this group should be
  configured to allow SSH (port 22) access for remote deployment/control
* Many instance properties are not configurable yet

Configuring Nodes
-----------------
At minimum, the following node properties need to be set:

  ``cloud.provider``
    Must be ``aws-ec2``.

  ``cloud.region``
    Data-center region code, one of ``us-west-1``, ``us-east-1``, ``eu-west-1`` or
    ``ap-southeast-1``

  ``cloud.image``
    The AMI image id of the image you want to instantiate.

  ``cloud.key-pair``
    Key-pair name **without** the ``.pem`` -suffix. **NOTE:** key-pairs are
    region-specific and will not work cross the data-centers.

  ``cloud.vm_name``
    Unique name for the VM. Provides the VM with a friendly name visible in
    the EC2 console.

  ``user``
    Username used to login to the system.

Creating a repository and a node from scratch::

  $ poni init
  $ poni add-node drumbo1
  $ poni set drumbo cloud.provider=aws-ec2 cloud.region=us-east-1 cloud.image=ami-daf615b3 cloud.key-pair=my-keypair user=root
  $ poni set drumbo1 cloud.vm_name=drumbo1
  $ poni set drumbo2 cloud.vm_name=drumbo2
  $ poni set drumbo3 cloud.vm_name=drumbo3
  $ poni set drumbo4 cloud.vm_name=drumbo4

In order to see the cloud properties you can use ``list -o``::

  $ poni list -o
      node drumbo1
     cloud     image:'ami-daf615b3' key-pair:'my-keypair' provider:'aws-ec2' region:'us-east-1'

While at it, why not create a few more instances::

  $ poni add-node "drumbo{id}" -n 2..4 -c -i drumbo1
  $ poni list -o
      node drumbo1
     cloud     image:'ami-daf615b3' key-pair:'my-keypair' provider:'aws-ec2' region:'us-east-1' vm_name:'drumbo1'
      node drumbo2 <= drumbo1
     cloud     image:'ami-daf615b3' key-pair:'my-keypair' provider:'aws-ec2' region:'us-east-1' vm_name:'drumbo2'
      node drumbo3 <= drumbo1
     cloud     image:'ami-daf615b3' key-pair:'my-keypair' provider:'aws-ec2' region:'us-east-1' vm_name:'drumbo3'
      node drumbo4 <= drumbo1
     cloud     image:'ami-daf615b3' key-pair:'my-keypair' provider:'aws-ec2' region:'us-east-1' vm_name:'drumbo4'

Option ``-i drumbo1`` means that the new nodes should be inherited from ``drumbo1`` and
``-c`` copies all node properties from the parent node while at it.

The ``<= drumbo1`` part in the output above tells us that the node is inherited from
``drumbo1``.

Now the nodes are ready to be started.

Starting Nodes
--------------
Creating node instances is done with the ``init`` -command::

  $ poni cloud init drumbo --wait
  poni    INFO    drumbo1: initialized: key-pair=u'my-keypair', region=u'us-east-1', instance=u'i-4c92cd21', image=u'ami-daf615b3', provider=u'aws-ec2', vm_name=u'drumbo1'
  poni    INFO    drumbo2: initialized: key-pair=u'my-keypair', region=u'us-east-1', instance=u'i-4e92cd23', image=u'ami-daf615b3', provider=u'aws-ec2', vm_name=u'drumbo2'
  poni    INFO    drumbo3: initialized: key-pair=u'my-keypair', region=u'us-east-1', instance=u'i-4692cd2b', image=u'ami-daf615b3', provider=u'aws-ec2', vm_name=u'drumbo3'
  poni    INFO    drumbo4: initialized: key-pair=u'my-keypair', region=u'us-east-1', instance=u'i-5c92cd31', image=u'ami-daf615b3', provider=u'aws-ec2', vm_name=u'drumbo4'
  aws-ec2 INFO    [0/4] instances 'running', waiting...
  aws-ec2 INFO    [0/4] instances 'running', waiting...
  aws-ec2 INFO    [0/4] instances 'running', waiting...
  aws-ec2 INFO    [0/4] instances 'running', waiting...
  aws-ec2 INFO    [0/4] instances 'running', waiting...
  aws-ec2 INFO    [1/4] instances 'running', waiting...
  poni    INFO    drumbo1: updated: host=u'ec2-50-16-65-176.compute-1.amazonaws.com' (from u''), private={'ip': u'10.253.202.50', 'dns': u'domU-12-31-38-01-C5-C4.compute-1.internal'} (from None)
  poni    INFO    drumbo2: updated: host=u'ec2-184-72-214-101.compute-1.amazonaws.com' (from u''), private={'ip': u'10.206.237.206', 'dns': u'domU-12-31-39-14-EE-24.compute-1.internal'} (from None)
  poni    INFO    drumbo3: updated: host=u'ec2-184-73-110-99.compute-1.amazonaws.com' (from u''), private={'ip': u'10.122.251.180', 'dns': u'ip-10-122-251-180.ec2.internal'} (from None)
  poni    INFO    drumbo4: updated: host=u'ec2-184-72-156-215.compute-1.amazonaws.com' (from u''), private={'ip': u'10.206.239.167', 'dns': u'domU-12-31-39-14-EC-59.compute-1.internal'} (from None)

First, each node is instantiated and they get their unique ``cloud.instance`` id, e.g.
``i-4c92cd21`` above.

Then Poni polls each instance's status until they are running. This behavior is
requested with the ``--wait`` -option.

Finally, when every instance is running, Poni updates the nodes' properties into the Poni
repository.

Now the cloud properties include the ``instance`` value::

  $ poni list -o
      node drumbo1
     cloud     image:'ami-daf615b3' instance:'i-4c92cd21' key-pair:'my-keypair' provider:'aws-ec2' region:'us-east-1' vm_name:'drumbo1'
      node drumbo2
     cloud     image:'ami-daf615b3' instance:'i-4e92cd23' key-pair:'my-keypair' provider:'aws-ec2' region:'us-east-1' vm_name:'drumbo2'
      node drumbo3
     cloud     image:'ami-daf615b3' instance:'i-4692cd2b' key-pair:'my-keypair' provider:'aws-ec2' region:'us-east-1' vm_name:'drumbo3'
      node drumbo4
     cloud     image:'ami-daf615b3' instance:'i-5c92cd31' key-pair:'my-keypair' provider:'aws-ec2' region:'us-east-1' vm_name:'drumbo4'

Also the node address information is updated to the node properties::

  $ poni list -p
      node drumbo1
      prop     depth:1 host:'ec2-50-16-65-176.compute-1.amazonaws.com' index:0 private:{dns:'domU-12-31-38-01-C5-C4.compute-1.internal' ip:'10.253.202.50'}
      node drumbo2
      prop     depth:1 host:'ec2-184-72-214-101.compute-1.amazonaws.com' index:1 parent:'drumbo1' private:{dns:'domU-12-31-39-14-EE-24.compute-1.internal' ip:'10.206.237.206'}
      node drumbo3
      prop     depth:1 host:'ec2-184-73-110-99.compute-1.amazonaws.com' index:2 parent:'drumbo1' private:{dns:'ip-10-122-251-180.ec2.internal' ip:'10.122.251.180'}
      node drumbo4
      prop     depth:1 host:'ec2-184-72-156-215.compute-1.amazonaws.com' index:3 parent:'drumbo1' private:{dns:'domU-12-31-39-14-EC-59.compute-1.internal' ip:'10.206.239.167'}

The following properties are updated:

  ``host``
    Full public internet DNS name
  ``private.dns``
    Full internal EC2 network hostname
  ``private.ip``
    Internal EC2 network IP-address

If the instance properties need to be updated later, the ``cloud update`` command can be
used. This can be done for example if instances have been initialized without the
``--wait`` -option, which does not update node address properties.


Assigning an elastic ip to an instance
---------------------------------------

You can assign elastic ip's to a running instance using  the ``cloud ip`` command. This command
uses the ``cloud.eip`` property value and assigns it to the instance.

  $ poni set drumbo1 cloud.eip=xxx.xxx.xxx.xxx
  $ poni cloud ip drumbo1

Checking Instance Status
------------------------
The ``list -q`` queries each cloud instances' status and shows it in the output::

  $ poni list -q
      node drumbo1
    status     running
      node drumbo2
    status     running
      node drumbo3
    status     running
      node drumbo4
    status     running

Terminating Instances
---------------------
To get rid of instances use the ``cloud terminate`` command::

  $ poni cloud terminate drumbo
  poni    INFO    terminated: drumbo1
  poni    INFO    terminated: drumbo2
  poni    INFO    terminated: drumbo3
  poni    INFO    terminated: drumbo4
  poni    INFO    4 instances terminated

The nodes are not actually terminated yet, but are 'shutting-down', which gives us a nice
excuse to try the ``cloud wait`` command::

  $ poni cloud wait drumbo --state=terminated
  aws-ec2 INFO    [0/4] instances 'terminated', waiting...
  aws-ec2 INFO    [0/4] instances 'terminated', waiting...
  aws-ec2 INFO    [3/4] instances 'terminated', waiting...
  aws-ec2 INFO    [3/4] instances 'terminated', waiting...
  poni    INFO    drumbo1: updated: host='' (from u'ec2-50-16-65-176.compute-1.amazonaws.com'), private={'ip': None, 'dns': ''} (from {u'ip': u'10.253.202.50', u'dns': u'domU-12-31-38-01-C5-C4.compute-1.internal'})
  poni    INFO    drumbo2: updated: host='' (from u'ec2-184-72-214-101.compute-1.amazonaws.com'), private={'ip': None, 'dns': ''} (from {u'ip': u'10.206.237.206', u'dns': u'domU-12-31-39-14-EE-24.compute-1.internal'})
  poni    INFO    drumbo3: updated: host='' (from u'ec2-184-73-110-99.compute-1.amazonaws.com'), private={'ip': None, 'dns': ''} (from {u'ip': u'10.122.251.180', u'dns': u'ip-10-122-251-180.ec2.internal'})
  poni    INFO    drumbo4: updated: host='' (from u'ec2-184-72-156-215.compute-1.amazonaws.com'), private={'ip': None, 'dns': ''} (from {u'ip': u'10.206.239.167', u'dns': u'domU-12-31-39-14-EC-59.compute-1.internal'})

``cloud wait`` polls each target nodes' status until all of them reach the given
``terminated`` status. It also empties node address properties once finished waiting.

Verifying that the instances are dead::

  $ poni list -q
      node drumbo1
    status     terminated
      node drumbo2
    status     terminated
      node drumbo3
    status     terminated
      node drumbo4
    status     terminated

.. include:: definitions.rst
