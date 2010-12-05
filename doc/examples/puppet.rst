===============================
Example: Poni Puppet Deployment
===============================

The files for this example are in the ``examples/puppet`` directory.

Preparations
------------
First, setup the AWS keys in environment variables::

  export AWS_ACCESS_KEY_ID=<access key>
  export AWS_SECRET_ACCESS_KEY=<secret key>

Edit ``inst-puppet.sh`` and replace your desired AWS key-pair name as the ``AWS_KEYPAIR`` value. NOTE: the name **MUST NOT** contain the trailing ``.pem``.

Drop your AWS key-pair to ``$HOME/.ssh/<aws-key-pair-name>.pem``


Creating the System
-------------------
The ``inst-puppet.sh`` contains the commands needed to create the Poni system for the
project::

  $ ./inst-puppet.sh
  create system
  > init
  > add-node template/ec2-deb6
  > add-config template/ec2-deb6 hacks
  > set template$ verify=bool:false
  > add-node software
  > set software$ verify=bool:false
  > add-config software puppet-master-v1.0
  > add-config software puppet-agent-v1.0
  > add-node puppet/master -i template/ec2-deb6
  > add-config puppet/master puppet-master -i software/puppet-master-v1.0
  > set puppet/master cloud.provider=aws-ec2 cloud.region=us-east-1 cloud.image=ami-daf615b3 cloud.kernel=aki-6eaa4907 cloud.ramdisk=ari-42b95a2b cloud.type=m1.small cloud.key-pair=aws-mel user=root
  > add-node nodes/demo/server{id:02} -n2 -i template/ec2-deb6
  > add-config nodes/demo/server puppet-agent -i software/puppet-agent-v1.0
  > set nodes/demo/server cloud.provider=aws-ec2 cloud.region=us-east-1 cloud.image=ami-daf615b3 cloud.kernel=aki-6eaa4907 cloud.ramdisk=ari-42b95a2b cloud.type=m1.small cloud.key-pair=aws-mel user=root

Let's see what got created::

  $ poni list -stci
    system nodes
    system     demo
      node         server01 <= template/ec2-deb6
    config             puppet-agent <= software/puppet-agent-v1.0
      node         server02 <= template/ec2-deb6
    config             puppet-agent <= software/puppet-agent-v1.0
    system puppet
      node     master <= template/ec2-deb6
    config         puppet-master <= software/puppet-master-v1.0
      node software
    config     puppet-master-v1.0
    config     puppet-agent-v1.0
    system template
      node     ec2-deb6
    config         hacks

View node cloud properties (not provisioned yet!)::

  $ poni list -o
      node nodes/demo/server01
     cloud ramdisk=u'ari-42b95a2b', kernel=u'aki-6eaa4907', key-pair=u'aws-mel', image=u'ami-daf615b3', provider=u'aws-ec2', type=u'm1.small', region=u'us-east-1'
      node nodes/demo/server02
     cloud ramdisk=u'ari-42b95a2b', kernel=u'aki-6eaa4907', key-pair=u'aws-mel', image=u'ami-daf615b3', provider=u'aws-ec2', type=u'm1.small', region=u'us-east-1'
      node puppet/master
     cloud ramdisk=u'ari-42b95a2b', kernel=u'aki-6eaa4907', key-pair=u'aws-mel', image=u'ami-daf615b3', provider=u'aws-ec2', type=u'm1.small', region=u'us-east-1'
      node software
      node template/ec2-deb6

Provisioning the VMs
--------------------
Provision VM instances from the cloud provider::

  $ poni cloud init . --wait
  poni    INFO    nodes/demo/server01: initialized: ramdisk=u'ari-42b95a2b', kernel=u'aki-6eaa4907', key-pair=u'aws-mel', instance=u'i-2318664e', provider=u'aws-ec2', region=u'us-east-1', type=u'm1.small', image=u'ami-daf615b3'
  poni    INFO    nodes/demo/server02: initialized: ramdisk=u'ari-42b95a2b', kernel=u'aki-6eaa4907', key-pair=u'aws-mel', instance=u'i-3f186652', provider=u'aws-ec2', region=u'us-east-1', type=u'm1.small', image=u'ami-daf615b3'
  poni    INFO    puppet/master: initialized: ramdisk=u'ari-42b95a2b', kernel=u'aki-6eaa4907', key-pair=u'aws-mel', instance=u'i-39186654', provider=u'aws-ec2', region=u'us-east-1', type=u'm1.small', image=u'ami-daf615b3'
  aws-ec2 INFO    [0/3] instances started, waiting...
  aws-ec2 INFO    [0/3] instances started, waiting...
  aws-ec2 INFO    [0/3] instances started, waiting...
  aws-ec2 INFO    [0/3] instances started, waiting...
  aws-ec2 INFO    [0/3] instances started, waiting...
  aws-ec2 INFO    [2/3] instances started, waiting...
  aws-ec2 INFO    [2/3] instances started, waiting...
  poni    INFO    nodes/demo/server01 update: host=u'ec2-174-129-167-134.compute-1.amazonaws.com', private={'ip': u'10.204.30.251', 'dns': u'ip-10-204-30-251.ec2.internal'}
  poni    INFO    nodes/demo/server02 update: host=u'ec2-184-72-190-127.compute-1.amazonaws.com', private={'ip': u'10.244.14.228', 'dns': u'ip-10-244-14-228.ec2.internal'}
  poni    INFO    puppet/master update: host=u'ec2-75-101-214-83.compute-1.amazonaws.com', private={'ip': u'10.244.14.4', 'dns': u'ip-10-244-14-4.ec2.internal'}

Query cloud instances statuses::

  $ poni list -qt
      node         server01
    status             running
      node         server02
    status             running
      node     master
    status         running
      node software
      node     ec2-deb6

Deployment
----------
Deploy the bootstrap files::

  $ poni deploy
  manager INFO       WROTE nodes/demo/server01: /root/deb6-upgrade.sh
  manager INFO       WROTE nodes/demo/server01: /root/inst-puppet-agent.sh
  manager INFO       WROTE nodes/demo/server02: /root/deb6-upgrade.sh
  manager INFO       WROTE nodes/demo/server02: /root/inst-puppet-agent.sh
  manager INFO       WROTE puppet/master: /root/deb6-upgrade.sh
  manager INFO       WROTE puppet/master: /root/inst-puppet-master.sh
  manager ERROR   puppet/master: /etc/puppet/manifests/site.pp: IOError: [Errno 2] No such file

.. note::
  deploying the puppetmaster ``site.pp`` manifest fails because puppetmaster has not yet
  been installed.

Bootstrap the Puppetmaster
--------------------------
Install puppetmaster on the master node::

  $ poni remote exec master ./inst-puppet-master.sh
  Get:1 http://http.us.debian.org squeeze Release.gpg [835B]
  Ign http://http.us.debian.org squeeze/main Translation-en_US
  Ign http://http.us.debian.org squeeze/contrib Translation-en_US

  ...

  Starting puppet master.
  Starting puppet queue.
  Setting up rake (0.8.7-2) ...
  Setting up rails-ruby1.8 (2.3.5-1.1) ...
  Setting up rails (2.3.5-1.1) ...
  Setting up ruby1.8-dev (1.8.7.302-2) ...
  Setting up unzip (6.0-4) ...
  Setting up zip (3.0-3) ...

Re-deploy the master configuration::

  $ poni deploy master
  manager INFO       WROTE puppet/master: /etc/puppet/manifests/site.pp

Review the automatically created puppetmaster ``site.pp`` manifest::

  $ poni remote exec master "cat /etc/puppet/manifests/site.pp"
  node 'default' {
    notice 'no specific rules for node'
  }

  class nginx {
    package { nginx:
      ensure => latest
    }

  #  service { nginx:
  #    running => true
  #  }
  }

  node 'ip-10-204-30-251.ec2.internal' {
    # poni node: nodes/demo/server01
    file { "/etc/sudoers":
        owner => root, group => root, mode => 440
    }

    include nginx
  }
  node 'ip-10-244-14-228.ec2.internal' {
    # poni node: nodes/demo/server02
    file { "/etc/sudoers":
        owner => root, group => root, mode => 440
    }

    include nginx
  }

Bootstrap Puppet Agents
-----------------------
Deploy puppet agents on the server nodes::

  $ poni remote exec demo/server -v ./inst-puppet-agent.sh
  --- BEGIN nodes/demo/server01 (ec2-174-129-167-134.compute-1.amazonaws.com): exec: './inst-puppet-agent.sh' ---
  Get:1 http://http.us.debian.org squeeze Release.gpg [835B]
  Ign http://http.us.debian.org squeeze/main Translation-en_US
  Ign http://http.us.debian.org squeeze/contrib Translation-en_US
  Ign http://http.us.debian.org squeeze/non-free Translation-en_US

  ...

  Setting up ruby (4.5) ...
  Starting puppet agent.
  --- END nodes/demo/server01 (ec2-174-129-167-134.compute-1.amazonaws.com): exec: './inst-puppet-agent.sh' ---

  --- BEGIN nodes/demo/server02 (ec2-184-72-190-127.compute-1.amazonaws.com): exec: './inst-puppet-agent.sh' ---
  Get:1 http://http.us.debian.org squeeze Release.gpg [835B]
  Ign http://http.us.debian.org squeeze/main Translation-en_US

  ...

  Starting puppet agent
  puppet not configured to start, please edit /etc/default/puppet to enable
  .
  Setting up ruby (4.5) ...
  Starting puppet agent.
  --- END nodes/demo/server02 (ec2-184-72-190-127.compute-1.amazonaws.com): exec: './inst-puppet-agent.sh' ---

Both the puppetmaster and the agents should now be running.

Check the certificate signing requests on the puppetmaster node::

  $ poni remote exec master "puppetca --list"
  ip-10-204-30-251.ec2.internal
  ip-10-244-14-228.ec2.internal

Sign all the requests::

  $ poni remote exec master "puppetca --sign --all"
  notice: Signed certificate request for ip-10-204-30-251.ec2.internal
  notice: Removing file Puppet::SSL::CertificateRequest ip-10-204-30-251.ec2.internal at '/var/lib/puppet/ssl/ca/requests/ip-10-204-30-251.ec2.internal.pem'
  notice: Signed certificate request for ip-10-244-14-228.ec2.internal
  notice: Removing file Puppet::SSL::CertificateRequest ip-10-244-14-228.ec2.internal at '/var/lib/puppet/ssl/ca/requests/ip-10-244-14-228.ec2.internal.pem'

Check puppet activity on the agent nodes::

  $ poni remote exec demo/server "grep puppet /var/log/syslog" -v

  --- BEGIN nodes/demo/server01 (ec2-174-129-167-134.compute-1.amazonaws.com): exec: 'grep puppet /var/log/syslog' ---
  Nov 23 20:55:29 ip-10-204-30-251 puppet-agent[1762]: Reopening log files
  Nov 23 20:57:31 ip-10-204-30-251 puppet-agent[1762]: Did not receive certificate
  Nov 23 20:59:31 ip-10-204-30-251 puppet-agent[1762]: Did not receive certificate
  Nov 23 21:01:31 ip-10-204-30-251 puppet-agent[1762]: Starting Puppet client version 2.6.2
  --- END nodes/demo/server01 (ec2-174-129-167-134.compute-1.amazonaws.com): exec: 'grep puppet /var/log/syslog' ---

  --- BEGIN nodes/demo/server02 (ec2-184-72-190-127.compute-1.amazonaws.com): exec: 'grep puppet /var/log/syslog' ---
  Nov 23 20:57:59 ip-10-244-14-228 puppet-agent[1762]: Reopening log files
  Nov 23 21:00:01 ip-10-244-14-228 puppet-agent[1762]: Did not receive certificate
  --- END nodes/demo/server02 (ec2-184-72-190-127.compute-1.amazonaws.com): exec: 'grep puppet /var/log/syslog' ---

Restart puppet agent to speed up the configuration process::

  $ poni remote exec demo/server "/etc/init.d/puppet restart"
  Restarting puppet agent.
  Restarting puppet agent.

Re-check the puppet activity from syslog::

  $ poni remote exec demo/server "grep puppet /var/log/syslog" -v
  --- BEGIN nodes/demo/server01 (ec2-174-129-167-134.compute-1.amazonaws.com): exec: 'grep puppet /var/log/syslog' ---
  Nov 23 20:55:29 ip-10-204-30-251 puppet-agent[1762]: Reopening log files
  Nov 23 20:57:31 ip-10-204-30-251 puppet-agent[1762]: Did not receive certificate
  Nov 23 20:59:31 ip-10-204-30-251 puppet-agent[1762]: Did not receive certificate
  Nov 23 21:01:31 ip-10-204-30-251 puppet-agent[1762]: Starting Puppet client version 2.6.2
  Nov 23 21:01:36 ip-10-204-30-251 puppet-agent[1762]: (/Stage[main]/Nginx/Package[nginx]/ensure) ensure changed 'purged' to 'latest'
  Nov 23 21:01:36 ip-10-204-30-251 puppet-agent[1762]: Finished catalog run in 3.30 seconds
  Nov 23 21:02:50 ip-10-204-30-251 puppet-agent[1762]: Caught TERM; calling stop
  Nov 23 21:02:53 ip-10-204-30-251 puppet-agent[1936]: Reopening log files
  Nov 23 21:02:53 ip-10-204-30-251 puppet-agent[1936]: Starting Puppet client version 2.6.2
  Nov 23 21:02:54 ip-10-204-30-251 puppet-agent[1936]: Finished catalog run in 0.29 seconds
  --- END nodes/demo/server01 (ec2-174-129-167-134.compute-1.amazonaws.com): exec: 'grep puppet /var/log/syslog' ---

  --- BEGIN nodes/demo/server02 (ec2-184-72-190-127.compute-1.amazonaws.com): exec: 'grep puppet /var/log/syslog' ---
  Nov 23 20:57:59 ip-10-244-14-228 puppet-agent[1762]: Reopening log files
  Nov 23 21:00:01 ip-10-244-14-228 puppet-agent[1762]: Did not receive certificate
  Nov 23 21:02:01 ip-10-244-14-228 puppet-agent[1762]: Starting Puppet client version 2.6.2
  Nov 23 21:02:05 ip-10-244-14-228 puppet-agent[1762]: (/Stage[main]/Nginx/Package[nginx]/ensure) ensure changed 'purged' to 'latest'
  Nov 23 21:02:05 ip-10-244-14-228 puppet-agent[1762]: Finished catalog run in 3.15 seconds
  Nov 23 21:02:57 ip-10-244-14-228 puppet-agent[1762]: Caught TERM; calling stop
  Nov 23 21:02:59 ip-10-244-14-228 puppet-agent[1931]: Reopening log files
  Nov 23 21:03:00 ip-10-244-14-228 puppet-agent[1931]: Starting Puppet client version 2.6.2
  Nov 23 21:03:01 ip-10-244-14-228 puppet-agent[1931]: Finished catalog run in 0.24 seconds
  --- END nodes/demo/server02 (ec2-184-72-190-127.compute-1.amazonaws.com): exec: 'grep puppet /var/log/syslog' ---

Puppet agent seems to have configured both nodes according to the site.pp manifests.

**Done!**

Cleanup
-------

...finally terminate the cloud instances and verify that they are stopped::

  $ poni cloud terminate .
  poni    INFO    3 instances terminated
  $ poni list -q
      node nodes/demo/server01
    status terminated
      node nodes/demo/server02
    status terminated
      node puppet/master
    status terminated
      node software
      node template/ec2-deb6
