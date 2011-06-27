import copy
import logging
import os
import random
import time
from . import errors
from . import cloudbase

try:
    from pyvsphere.vim25 import Vim, ManagedObject
    pyvsphere_available = True
except ImportError:
    pyvsphere_available = False

class VSphereProvider(cloudbase.Provider):
    def __init__(self, cloud_prop):
        self.log = logging.getLogger('poni.vsphere')
        self.vi_url = os.environ.get('VI_URL') or cloud_prop.get("vi_url")
        assert self.vi_url, "either the enviroment variable VI_URL or vcenter_url property must be set for vSphere instances"
        self.vi_username = os.environ.get('VI_USERNAME') or cloud_prop.get("vi_username")
        assert self.vi_username, "either the enviroment variable VI_USERNAME or vi_username property must be set for vSphere instances"
        self.vi_password = os.environ.get('VI_PASSWORD') or cloud_prop.get("vi_password")
        assert self.vi_password, "either the enviroment variable VI_PASSWORD or vi_password property must be set for vSphere instances"
        assert pyvsphere_available, "pyvsphere must be installed for vSphere instances to work"
        self.vim = Vim(self.vi_url)
        self.vim.login(self.vi_username, self.vi_password)
        self.instances = {}
        self.vms = None
        self._base_vm_cache = {}
        self._cluster_datastore_cache = {}

    @classmethod
    def get_provider_key(cls, cloud_prop):
        """
        Return a cloud Provider object for the given cloud properties.
        """
        return "vSphere"

    def _get_instance(self, prop):
        """
        Get a VM instance either a cache or directly from vSphere and
        establish the current state of the VM.
        """
        vm_name = instance_id = prop.get('vm_name', None)
        assert vm_name, "vm_name must be specified for vSphere instances"
        base_vm_name = prop.get('base_vm_name', None)
        assert base_vm_name, "base_vm_name must be specified for vSphere instances"
        placement = prop.get('placement', None)
        resource_pool = prop.get('resource_pool', None)
        cluster = prop.get('cluster', None)
        datastore = prop.get('datastore', None)
        datastore_filter = prop.get('datastore_filter', '')
        hardware = prop.get('hardware', None)
        instance = self.instances.get(instance_id)
        if not instance:
            vm = None
            vm_state = 'VM_NON_EXISTENT'
            # self.vms is a cache mechanism to get around the fact
            # that vim.find_vm_by_name is O(N*M) in time complexity
            if self.vms is None:
                self.vms = {}
                for e in self.vim.find_entities_by_type('VirtualMachine', ['summary', 'snapshot']) or []:
                    self.vms[e.name] = e
            vm = self.vms.get(vm_name)
            if vm:
                self.log.debug('VM %s already exists', vm_name)
                vm_state = 'VM_DIRTY'
                if (hasattr(vm, 'snapshot') and
                    vm.snapshot.rootSnapshotList and
                    vm.snapshot.rootSnapshotList[0].name == 'pristine'):
                    vm_state = 'VM_CLEAN'
                    if vm.power_state() == 'poweredOn':
                        vm_state = 'VM_RUNNING'
            self.log.debug("Instance %s is in %s state", vm_name, vm_state)
            instance = dict(id=instance_id, vm=vm, vm_name=vm_name,
                            base_vm_name=base_vm_name, vm_state=vm_state,
                            placement=placement, resource_pool=resource_pool, cluster=cluster,
                            datastore=datastore, datastore_filter=datastore_filter, hardware=hardware)
            self.instances[instance_id] = instance
        return instance

    def init_instance(self, cloud_prop):
        """
        Create a new instance with the given properties.

        Returns node properties that are changed.
        """
        instance = self._get_instance(cloud_prop)
        # Establish the current state of VM
        out_prop = copy.deepcopy(cloud_prop)
        # Limit the state to VM_CLEAN at best so init will have to revert the snapshot, at least
        instance["vm_state"] = 'VM_CLEAN' if instance['vm_state'] == 'VM_RUNNING' else instance['vm_state']
        out_prop["instance"] = instance['id']
        return dict(cloud=out_prop)

    def get_instance_status(self, prop):
        """
        Return instance status string for the instance specified in the given
        cloud properties dict.
        """
        instance = self._get_instance(prop)
        return instance["vm_state"]

    def terminate_instances(self, props):
        """
        Terminate instances specified in the given sequence of cloud
        properties dicts.
        """
        jobs = {}
        tasks = {}
        for prop in props:
            instance_id = prop['instance']
            instance = self._get_instance(prop)
            assert instance, "instance %s not found. Very bad. Should not happen. Ever." % instance_id
            vm_state = instance['vm_state']
            if vm_state != 'VM_NON_EXISTENT':
                jobs[instance_id] = self._delete_vm(instance)
                tasks[instance_id] = None
        while jobs:
            if [tasks[x] for x in tasks if tasks[x]]:
                _,tasks = self.vim.update_many_objects(tasks)
            for instance_id in list(jobs):
                try:
                    job = jobs[instance_id]
                    # This is where the magic happens: the generator is fed the
                    # latest updated Task and returns the same or the next one
                    # to poll.
                    tasks[instance_id] = job.send(tasks[instance_id])
                except StopIteration:
                    del tasks[instance_id]
                    del jobs[instance_id]
            self.log.info("[%s/%s] instances being terminated, waiting...", len(props)-len(jobs), len(props))
            time.sleep(2)

    def wait_instances(self, props, wait_state="running"):
        """
        Wait for all the given instances to reach status specified by
        the 'wait_state' argument.

        Returns a dict {instance_id: dict(<updated properties>)}

        @note: This function uses generators to simulate co-operative,
               non-blocking multitasking. The generators generate and
               get fed a sequence of Task status objects. Once the
               generator is done, it will simply exit.
               All this complexity is necessary to work around the
               problem that each of the jobs might takes ages to finish,
               hence doing them in a sequential order is highly undesirable.
        """
        jobs = {}
        tasks = {}
        updated_props = {}
        error_count = 0
        # 8 is a magical value from experience, infinity (None/0)
        # causes some cloning operations to fail. vCenter itself
        # queues things nicely, but it gets "Resources currently in
        # use by other operations. Waiting." probably from disk, and
        # finally fails. So this value might be hardware configuration
        # dependent (number of LUNs, hosts etc.).
        #
        # As an example, 21 concurrent clones caused 4 errors to occur
        # on configuration with six datastores (LUNs) and 7 ESX hosts.
        max_jobs = 8

        # Keep creating and running the jobs until they are all done
        while props or jobs:
            while (not max_jobs or len(jobs) < max_jobs) and props:
                prop = props.pop(0)
                self.log.info("prop=%r len(props)=%d", prop, len(props))
                instance_id = prop['instance']
                instance = self._get_instance(prop)
                assert instance, "instance %s not found. Very bad. Should not happen. Ever." % instance_id
                vm_state = instance['vm_state']
                job = None
                if wait_state == 'running':
                    # Get the VM running from whatever state it's in
                    if vm_state == 'VM_CLEAN':
                        job = self._revert_vm(instance)
                    elif vm_state == 'VM_NON_EXISTENT':
                        job = self._clone_vm(instance, nuke_old=True)
                    elif vm_state == 'VM_DIRTY':
                        job = self._clone_vm(instance, nuke_old=True)
                else:
                    # Handle the update
                    if vm_state == 'VM_RUNNING':
                        job = self._update_vm(instance)
                if job:
                    jobs[instance_id] = job
                    tasks[instance_id] = None

            if jobs:
                if [tasks[x] for x in tasks if tasks[x]]:
                    _,tasks = self.vim.update_many_objects(tasks)
                for instance_id in list(jobs):
                    try:
                        job = jobs[instance_id]
                        # This is where the magic happens: the generator is fed the
                        # latest updated Task and returns the same or the next one
                        # to poll.
                        tasks[instance_id] = job.send(tasks[instance_id])
                    except StopIteration:
                        self.log.debug("%s entered state: %s", instance_id, wait_state)
                        del tasks[instance_id]
                        del jobs[instance_id]
                        self.instances[instance_id]['vm_state'] = 'VM_RUNNING'
                        # Collect the IP address which should be in there by now
                        ipv4=self.instances[instance_id]['ipv4']
                        private=dict(ip=ipv4,
                                     dns=ipv4)
                        updated_props[instance_id] = dict(host=ipv4, private=private)
                    except Exception, err:
                        self.log.error("%s failed: %s", instance_id, err)
                        del tasks[instance_id]
                        del jobs[instance_id]
                        error_count += 1

                # self.log.info("[%s/%s] instances %r, waiting...", len(updated_props), len(props), wait_state)
                self.log.debug("#props=%d #jobs=%d errors=%d", len(props), len(jobs), error_count)
                time.sleep(2)

        if error_count:
            raise errors.CloudError("%d jobs failed" % error_count)

        return updated_props

    def _get_base_vm(self, instance):
        """
        Get a VM object for the base image for cloning with a bit of caching

        @param base_vm_name: name of the VM to find

        @returns: VM object or None if not found
        """
        base_vm_name = instance['base_vm_name']
        datastore_filter = instance['datastore_filter']
        cluster = instance['cluster']
        base_vm = self._base_vm_cache.get(base_vm_name, None)
        if not base_vm:
            base_vm = self.vim.find_vm_by_name(base_vm_name, ['storage', 'summary'])
            if base_vm:
                base_vm.size = sum([x.committed for x in base_vm.storage.perDatastoreUsage])
                assert base_vm.size > 0, "base vm size is zero? Very unlikely..."
                if cluster:
                    datastores = self._datastores_in_cluster(cluster)
                else:
                    datastores = self.vim.find_entities_by_type('Datastore', ['name', 'summary', 'info'])
                # List all available datastores that contain <datastore_filter> as substring
                base_vm.available_datastores = [x for x in datastores if datastore_filter in x.name]
                self.log.debug("Datastores for VM %s: %s" % (base_vm_name, ','.join([x.name for x in base_vm.available_datastores])))
                self._base_vm_cache[base_vm_name] = base_vm
        return base_vm

    def _datastores_in_cluster(self, clustername):
        """ Find and return the list of available datastores for a ClusterComputeResource """
        if clustername not in self._cluster_datastore_cache:
            ccr = self.vim.find_entity_by_name('ClusterComputeResource', clustername, ['name', 'datastore'])
            assert ccr, "specified ClusterComputeResource '%s' not found" % clustername
            datastores = [ManagedObject(x, self.vim, ['name', 'summary', 'info']) for x in ccr.datastore]
            self._cluster_datastore_cache[clustername] = datastores
        return self._cluster_datastore_cache.get(clustername, [])

    def _clone_vm(self, instance, nuke_old=False):
        """
        Perform a full clone-poweron-snapshot cycle on the instance

        This is a generator function which is used in a co-operative
        multitasking manner. See wait_instances() for an idea on its
        usage.

        @param instance: dict of the VM instance to create
        @param nuke_old: should an existing VM with the same be nuked

        @return: generator function
        """
        def done(task):
            return (hasattr(task, 'info') and
                    (task.info.state == 'success' or
                     task.info.state == 'error'))

        def got_ip(task):
            return (hasattr(task, 'summary') and
                    getattr(task.summary.guest, 'ipAddress', None))

        def place_vm(base_vm, placement_strategy='random'):
            """ Place the VM to the available datastores either randomly or wherever there is most space """
            assert placement_strategy in ['random', 'most-space'], "unknown placement strategy, must be either 'random' or 'most-space'"
            # Make a list of datastores that have enough space and sort it by free space
            possible_targets = sorted([x for x in base_vm.available_datastores if x.summary.freeSpace > base_vm.size], key=lambda x: x.summary.freeSpace, reverse=True)
            assert len(possible_targets) > 0, "no suitable datastore found. Are they all low on space?"
            if placement_strategy == 'random':
                target = random.choice(possible_targets)
            if placement_strategy == 'most-space':
                target = possible_targets[0]
            target.summary.freeSpace -= base_vm.size
            return target

        vm_name = instance['vm_name']
        base_vm = self._get_base_vm(instance)
        assert base_vm, "base VM %s not found, check the cloud.base_vm_name property for %s" % (instance['base_vm_name'], vm_name)

        if nuke_old:
            clone = self.vim.find_vm_by_name(vm_name, ['summary'])
            if clone:
                if clone.power_state() == 'poweredOn':
                    self.log.debug("CLONE(%s) POWEROFF STARTING" % vm_name)
                    task = clone.power_off_task()
                    while not done(task):
                        task = (yield task)
                    self.log.debug("CLONE(%s) POWEOFF DONE" % vm_name)
                self.log.debug("CLONE(%s) DELETE STARTING" % vm_name)
                task = clone.delete_vm_task()
                while not done(task):
                    task = (yield task)
                self.log.debug("CLONE(%s) DELETE DONE" % vm_name)

        # Use the specified target datastore or pick one automagically based on the placement strategy
        if instance['datastore']:
            datastore=instance['datastore']
        else:
            placement_strategy = instance['placement'] or 'random'
            datastore=place_vm(base_vm, placement_strategy=placement_strategy)

        self.log.debug("CLONE(%s) CLONE STARTING" % vm_name)
        task = base_vm.clone_vm_task(vm_name, linked_clone=False, datastore=datastore, resource_pool=instance['resource_pool'])
        while not done(task):
            task = (yield task)
        self.log.debug("CLONE(%s) CLONE DONE" % vm_name)

        clone = self.vim.find_vm_by_name(vm_name)

        # Reconfigure the VM hardware as specified
        hardware = instance["hardware"]
        if hardware:
            # Find if any new disks or NICs need to be added to the VM
            disks = [hardware.get("disk%d" % x) for x in xrange(10) if hardware.get("disk%d" % x)]
            nics = [hardware.get("nic%d" % x) for x in xrange(10) if hardware.get("nic%d" % x)]
            spec = self.vim.create_object('VirtualMachineConfigSpec')
            if hardware["ram"]:
                spec.memoryMB = int(hardware["ram"])
            if hardware["cpus"]:
                spec.numCPUs = int(hardware["cpus"])
            for disk in disks:
                provisioning = disk.get("provisioning", "thin")
                assert provisioning in ["thin", "thick"], "disk provisioning must be either 'thick' or 'thin', not %s" % provisioning
                disk_mode = disk.get("mode", "persistent")
                disk_spec = clone.spec_new_disk(size=int(disk["size"]), thin=provisioning=='thin', disk_mode=disk_mode)
                spec.deviceChange.append(disk_spec)
            for nic in nics:
                network = nic.get("network")
                assert network, "network name must be specified for NICs"
                nic_type = nic.get("nic_type", "vmxnet2")
                nic_spec = clone.spec_new_nic(network=network, nic_type=nic_type)
                spec.deviceChange.append(nic_spec)

            self.log.debug("CLONE(%s) RECONFIG_VM STARTING" % vm_name)
            task = clone.reconfig_vm_task(spec=spec)
            while not done(task):
                task = (yield task)
            self.log.debug("CLONE(%s) RECONFIG_VM DONE" % vm_name)

        assert clone, "Could not clone vm %s" % (vm_name)

        self.log.debug("CLONE(%s) POWERON STARTING" % vm_name)
        task = clone.power_on_task()
        while not done(task):
            task = (yield task)
        clone.update_local_view(['summary'])
        assert clone.power_state() == 'poweredOn', "%s was not successfully powered on" % vm_name
        self.log.debug("CLONE(%s) POWERON DONE" % vm_name)

        self.log.debug("CLONE(%s) WAITING FOR IP" % (vm_name))
        task = clone
        while not got_ip(task):
            task = (yield task)
        self.log.debug("CLONE(%s) GOT IP: %s" % (vm_name, task.summary.guest.ipAddress))
        instance['ipv4'] = task.summary.guest.ipAddress

        self.log.debug("CLONE(%s) SNAPSHOT STARTING" % vm_name)
        task = clone.create_snapshot_task('pristine', memory=True)
        while not done(task):
            task = (yield task)
        self.log.debug("CLONE(%s) SNAPSHOT DONE" % vm_name)

    def _revert_vm(self, instance):
        """
        Perform a quick snapshot revert on a VM instance

        This is a generator function which is used in a co-operative
        multitasking manner. See wait_instances() for an idea on its
        usage.

        @param instance: dict of the VM instance to create

        @return: generator function
        """
        def done(task):
            return (hasattr(task, 'info') and
                    (task.info.state == 'success' or
                     task.info.state == 'error'))

        def got_ip(task):
            return (hasattr(task, 'summary') and
                    getattr(task.summary.guest, 'ipAddress', None))

        vm_name = instance['vm_name']
        vm = instance['vm']
        if not vm:
            vm = self.vim.find_vm_by_name(vm_name)
        assert vm, "VM %s not found in vSphere, something is terribly wrong here" % vm_name

        self.log.debug("REVERT(%s) STARTING" % vm_name)
        task = vm.revert_to_current_snapshot_task()
        while not done(task):
            task = (yield task)
        self.log.debug("REVERT(%s) DONE" % vm_name)

        self.log.debug("REVERT(%s) WAITING FOR IP" % (vm_name))
        task = vm
        while not got_ip(task):
            task = (yield task)
        self.log.debug("REVERT(%s) GOT IP: %s" % (vm_name, task.summary.guest.ipAddress))
        instance['ipv4'] = task.summary.guest.ipAddress

    def _delete_vm(self, instance):
        """
        Power off and delete a VM

        This is a generator function which is used in a co-operative
        multitasking manner. See wait_instances() for an idea on its
        usage.

        @param instance: dict of the VM instance to delete

        @return: generator function
        """
        def done(task):
            return (hasattr(task, 'info') and
                    (task.info.state == 'success' or
                     task.info.state == 'error'))

        vm_name = instance['vm_name']
        vm = instance['vm']
        if not vm:
            vm = self.vim.find_vm_by_name(vm_name, ['summary'])
        assert vm, "VM %s not found in vSphere, something is terribly wrong here" % vm_name

        if vm.power_state() == 'poweredOn':
            self.log.debug("DELETE(%s) POWEROFF STARTING" % vm_name)
            task = vm.power_off_task()
            while not done(task):
                task = (yield task)
            vm.update_local_view(['summary'])
            assert vm.power_state() == 'poweredOff', "%s was not successfully powered off" % vm_name
            self.log.debug("DELETE(%s) POWEROFF DONE" % vm_name)

        self.log.debug("DELETE(%s) DELETE STARTING" % vm_name)
        task = vm.delete_vm_task()
        while not done(task):
            task = (yield task)
        self.log.debug("DELETE(%s) DELETE DONE" % vm_name)

    def _update_vm(self, instance):
        """
        Get updated info from the VM instance

        This is a generator function which is used in a co-operative
        multitasking manner. See wait_instances() for an idea on its
        usage.

        @param instance: dict of the VM instance to update

        @return: generator function
        """
        def got_ip(task):
            return (hasattr(task, 'summary') and
                    getattr(task.summary.guest, 'ipAddress', None))

        vm_name = instance['vm_name']
        vm = instance['vm']
        if not vm:
            vm = self.vim.find_vm_by_name(vm_name)
        assert vm, "VM %s not found in vSphere, something is terribly wrong here" % vm_name

        self.log.debug("UPDATE(%s) WAITING FOR IP" % (vm_name))
        task = vm
        while not got_ip(task):
            task = (yield task)
        self.log.debug("UPDATE(%s) GOT IP: %s" % (vm_name, task.summary.guest.ipAddress))
        instance['ipv4'] = task.summary.guest.ipAddress
