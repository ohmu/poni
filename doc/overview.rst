Overview
========
Poni is a systems management tool for defining, deploying and verifying complex
multi-node computer systems.

Poni helps managing systems in many ways:

* Systems, nodes, installed software and settings are stored in a central Poni
  repository, so there is a single location where the system is defined and
  documented.
* Changes to the Poni repository can be version-controlled with Git_ allowing
  rollback and access to history of configuration changes.
* Applications are configured by rendering configuration templates, using a
  powerful template language (such as Cheetah_) reducing the need to write
  application-specific installation or configuration scripts.
* The entire system configuration is available when creating node-specific
  configuration files, making it easy to wire multiple nodes together.
* Virtual machines can be easily provisioned from a cloud provider (currently
  `Amazon EC2`_ is supported).

Challenges
----------
These are some of the challenges that Poni attemps to address:

* Full automation (read: scriptability) support.
* Deployment so easy and repeatable that all developers, testers, admins and
  support engineers are able to rollout their own playground environments.
* Repeatable multi-tier software deployment.
* Configuring N frontend nodes to talk to M backend nodes. What happens when
  you add or remove a few nodes?
* Auditable configuration management over as much as possible of the deployed
  software stack.
* Integrating with multiple hypervisor (or "cloud") providers.
* Optimizing the total time spent deploying a build from scratch for
  development and testing purposes.
* Traceability for configuration changes.
* Complexity of deploying different management systems.
* License cost and poor feature match of proprietary hypervisor
  implementations for fast-paced development activities.
* Managing configurations of any existing 3rd party and open-source software
  included in the solution stack.
* Common interface for configuring settings for all of the components in the
  stack.
* Producing reliable, up-to-date information regarding network addresses and
  the different network connections between nodes.
* Deep integration with the software stack that is deployed.
* Zero-downtime upgrades for a multi-tier, redundant system.
* Dynamic deployment for nodes and different features: must be able to leave
  out sub-systems and large features and still be able to deploy a whole,
  functional environment.
* Post-deployment administrative operations: starting/stopping components,
  online/offline nodes, checking node/component status, etc.
* Deployment-time dependencies (e.g. DB backends are deployed before DB
  frontends, package repository is deployed before nodes that require packages
  from it).

Solutions
---------
* Built for automation: all commands can be run from scripts, parameterized
  and with proper exit codes.
* Provides a holistic view to the entire system, all the nodes and their
  settings for configration file templates.
* Provides a ``poni audit`` command for verifying all deployed files. Can also
  diff the "unauthorized" changes.
* Possible to support multiple hypervisors.
* Deployment is fast enough to be done from scratch for most purposes. Base
  VM images do not contain any software, which helps reducing manual CM effort.
* The entire system configuration is stored in a single directory tree that
  is version controlled using Git. Full history of changes is visible as
  commits.
* Dynamic information collection from templates: pieces of information can be
  collected and reports produced out of them. Allows drawing network diagrams,
  defining firewall rules, etc.
* Provides multiple ways of controlling the deployed software post-deployment:
  custom "control commands" which are written in Python or simply by running
  shell commands over a specific set of nodes.
* Custom control commands can have dependencies: useful for installation
  commands that need to be executed in a certain order.

How Poni is Used
----------------
#. Bundle software-specific configuration file templates and installation
   scripts into "Poni configs". Typically one config represent one software
   component (for example DB, monitoring agent, HTTP server, etc.) Custom
   remote commands (e.g. for executing the installation script) are also
   defined in this step.
#. Create node templates for the different node types. Configure each node
   type to include one or more Poni configs.
#. Instantiate the node templates into node instances. Multiple nodes can
   be created from a single node template. (``poni create-node``)
#. (Optional) Automatically provision the nodes from a private or public
   cloud provider. Can also use pre-created HW-based nodes or pre-deployed
   VMs. (``poni cloud init``)
#. Deploy the templates, software packages and installation scripts to the
   hosts. (``poni deploy``)
#. Run the installation scripts. (``poni control NODES COMMAND``)
#. DONE, system is up and running.

The node creation, VM provisioning and software deployment steps are typically
executed from a single script in order to provide an easy method of deploying
from scratch.

