Node Remote Control
===================
Commands can be executed on remote nodes using Poni's ``remote exec`` and
``remote shell`` commands.

Commands are executed over an SSH connection unless the node ``deploy`` property has been
set to ``local``. In that case, the commands are simply run locally in the current host.

Remote Execution of Shell Commands
----------------------------------
Having already setup our system::

  $ poni list
      node web/database
      node web/frontend1
      node web/frontend2
      node web/frontend3
      node web/frontend4

Let's run the ``last`` command on all of the frontend nodes::

  $ poni remote exec frontend last
  reboot   system boot  2.6.21.7-2.fc8xe Sat Dec  4 23:10 - 23:20  (00:09)

  wtmp begins Sat Dec  4 23:10:36 2010
  reboot   system boot  2.6.21.7-2.fc8xe Sat Dec  4 23:10 - 23:20  (00:09)

  wtmp begins Sat Dec  4 23:10:31 2010
  reboot   system boot  2.6.21.7-2.fc8xe Sat Dec  4 23:10 - 23:20  (00:09)

  wtmp begins Sat Dec  4 23:10:40 2010
  reboot   system boot  2.6.21.7-2.fc8xe Sat Dec  4 23:10 - 23:20  (00:09)

  wtmp begins Sat Dec  4 23:10:45 2010

All good, except we don't know which output comes from which node. The ``-v`` option
helps with that::

  $ poni remote exec frontend last -v
  --- BEGIN web/frontend1 (ec2-184-72-68-108.compute-1.amazonaws.com): exec: 'last' ---
  reboot   system boot  2.6.21.7-2.fc8xe Sat Dec  4 23:10 - 23:23  (00:12)

  wtmp begins Sat Dec  4 23:10:36 2010
  --- END web/frontend1 (ec2-184-72-68-108.compute-1.amazonaws.com): exec: 'last' ---

  --- BEGIN web/frontend2 (ec2-184-72-72-65.compute-1.amazonaws.com): exec: 'last' ---
  reboot   system boot  2.6.21.7-2.fc8xe Sat Dec  4 23:10 - 23:23  (00:12)

  wtmp begins Sat Dec  4 23:10:31 2010
  --- END web/frontend2 (ec2-184-72-72-65.compute-1.amazonaws.com): exec: 'last' ---

  --- BEGIN web/frontend3 (ec2-67-202-44-0.compute-1.amazonaws.com): exec: 'last' ---
  reboot   system boot  2.6.21.7-2.fc8xe Sat Dec  4 23:10 - 23:23  (00:12)

  wtmp begins Sat Dec  4 23:10:40 2010
  --- END web/frontend3 (ec2-67-202-44-0.compute-1.amazonaws.com): exec: 'last' ---

  --- BEGIN web/frontend4 (ec2-50-16-50-77.compute-1.amazonaws.com): exec: 'last' ---
  reboot   system boot  2.6.21.7-2.fc8xe Sat Dec  4 23:10 - 23:23  (00:12)

  wtmp begins Sat Dec  4 23:10:45 2010
  --- END web/frontend4 (ec2-50-16-50-77.compute-1.amazonaws.com): exec: 'last' ---

The command is executed in shell, so multiple commands, piping, etc. is ok::

  $ poni remote exec frontend1 "last | head -1"
  reboot   system boot  2.6.21.7-2.fc8xe Sat Dec  4 23:10 - 23:25  (00:14)
  $ poni remote exec frontend1 "id; whoami; pwd"
  uid=0(root) gid=0(root) groups=0(root)
  root
  /root

Remote Interactive Shell
------------------------
``remote shell`` opens an interactive shell connection the the remote node::

  $ poni remote shell frontend1 -v
  --- BEGIN web/frontend1 (ec2-184-72-68-108.compute-1.amazonaws.com): shell ---
  Linux ip-10-122-179-29 2.6.21.7-2.fc8xen-ec2-v1.0 #2 SMP Tue Sep 1 10:04:29 EDT 2009 i686

  ip-10-122-179-29:~# echo "hello, world"
  hello, world
  ip-10-122-179-29:~# exit
  logout
  --- END web/frontend1 (ec2-184-72-68-108.compute-1.amazonaws.com): shell ---


.. include:: definitions.rst
