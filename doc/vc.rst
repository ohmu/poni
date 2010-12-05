Repository Version Control
==========================
Poni supports basic version control operations for its repository using the Git_ version
control system.

Initializing Version Control
----------------------------
After you have created your Poni repository, you can start version controlling it using
the ``vc init`` command::

  $ poni init
  $ poni add-node "web/frontend{id}" -n 4
  $ poni vc init

``vc init`` automatically commits everything currently in the repository as the first
revision::

  $ git log
  commit ab99567c71d26c787aea5f8ceedae5ade4e89205
  Author: user <user@host.local>
  Date:   Sun Dec 5 01:41:23 2010 +0300

      initial commit

Committing Changes
------------------
Now let's make some changes::

  $ poni set frontend2 host=fe2.company.com
  $ poni add-node web/database

The working set can be compared with the last commit using the ``vc diff`` command::

  $ poni vc diff
  Changes:
  diff --git a/system/web/frontend2/node.json b/system/web/frontend2/node.json
  index 4a921a3..27f7588 100644
  --- a/system/web/frontend2/node.json
  +++ b/system/web/frontend2/node.json
  @@ -1,3 +1,3 @@
   {
  -    "host": ""
  +    "host": "fe2.company.com"
   }
  \ No newline at end of file

  Untracked files:
    system/web/database/node.json

Changes can be committed using the ``vc checkpoint <message>`` command that automatically
adds all added files and commits changed files::

  $ poni vc checkpoint "added a db node and adjusted things"

Now we have two revisions::

  $ git log
  commit 6a750b460c2d13d35b83fa24e3e81060e409fe57
  Author: user <user@host.local>
  Date:   Sun Dec 5 01:52:43 2010 +0300

      added a db node and adjusted things

  commit ab99567c71d26c787aea5f8ceedae5ade4e89205
  Author: user <user@host.local>
  Date:   Sun Dec 5 01:41:23 2010 +0300

      initial commit

The last commits contains the changes we made::

  $ git show
  commit 6a750b460c2d13d35b83fa24e3e81060e409fe57
  Author: user <user@host.local>
  Date:   Sun Dec 5 01:52:43 2010 +0300

      added a db node and adjusted things

  diff --git a/system/web/database/node.json b/system/web/database/node.json
  new file mode 100644
  index 0000000..4a921a3
  --- /dev/null
  +++ b/system/web/database/node.json
  @@ -0,0 +1,3 @@
  +{
  +    "host": ""
  +}
  \ No newline at end of file
  diff --git a/system/web/frontend2/node.json b/system/web/frontend2/node.json
  index 4a921a3..27f7588 100644
  --- a/system/web/frontend2/node.json
  +++ b/system/web/frontend2/node.json
  @@ -1,3 +1,3 @@
   {
  -    "host": ""
  +    "host": "fe2.company.com"
   }
  \ No newline at end of file

.. include:: definitions.rst
