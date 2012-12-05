"""
Copyright 2011 F-Secure Corporation

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import copy
import logging
import os
import time
from . import errors
from . import cloudbase

try:
    from pyvsphere.vim25 import Vim
    from pyvsphere.vmops import VmOperations
    pyvsphere_available = True
except ImportError:
    pyvsphere_available = False

class VSphereProvider(cloudbase.Provider):
    def __init__(self, cloud_prop):
        cloudbase.Provider.__init__(self, 'vsphere', cloud_prop)
        self.log = logging.getLogger('poni.vsphere')
        self.vi_url = os.environ.get('VI_URL') or cloud_prop.get("vi_url")
        assert self.vi_url, "either the enviroment variable VI_URL or vcenter_url property must be set for vSphere instances"
        self.vi_username = os.environ.get('VI_USERNAME') or cloud_prop.get("vi_username")
        assert self.vi_username, "either the enviroment variable VI_USERNAME or vi_username property must be set for vSphere instances"
        self.vi_password = os.environ.get('VI_PASSWORD') or cloud_prop.get("vi_password")
        assert self.vi_password, "either the enviroment variable VI_PASSWORD or vi_password property must be set for vSphere instances"
        self.vi_version = os.environ.get('VI_VERSION') or cloud_prop.get("vi_version")
        assert pyvsphere_available, "pyvsphere must be installed for vSphere instances to work"
        self.vim = Vim(self.vi_url, version=self.vi_version)
        self.vim.login(self.vi_username, self.vi_password)
        self.vmops = VmOperations(self.vim)
        self.instances = {}
        self.vms = None

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
        placement = prop.get('placement', 'random')
        resource_pool = prop.get('resource_pool', None)
        cluster = prop.get('cluster', None)
        datastore = prop.get('datastore', None)
        datastore_filter = prop.get('datastore_filter', '')
        hardware = prop.get('hardware', None)
        folder = prop.get('folder', None)
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
                            datastore=datastore, datastore_filter=datastore_filter, hardware=hardware,
                            folder=folder)
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
                jobs[instance_id] = self.vmops.delete_vm(instance)
                tasks[instance_id] = None
        while jobs:
            if [tasks[x] for x in tasks if tasks[x]]:
                _, tasks = self.vim.update_many_objects(tasks)
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
        props = props[:] # make a copy because we pop() from it
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
        max_jobs = int(os.environ.get("PONI_MAX_VSPHERE_JOBS", 8))

        # Keep creating and running the jobs until they are all done
        next_report = time.time() + 10.0
        while props or jobs:
            while (not max_jobs or len(jobs) < max_jobs) and props:
                prop = props.pop(0)
                instance_id = prop['instance']
                instance = self._get_instance(prop)
                assert instance, "instance %s not found. Very bad. Should not happen. Ever." % instance_id
                vm_state = instance['vm_state']
                job = None
                if wait_state == 'running':
                    # Get the VM running from whatever state it's in
                    if vm_state == 'VM_CLEAN':
                        job = self.vmops.revert_to_snapshot(instance)
                    elif vm_state == 'VM_NON_EXISTENT':
                        job = self.vmops.clone_vm(instance, nuke_old=True)
                    elif vm_state == 'VM_DIRTY':
                        job = self.vmops.clone_vm(instance, nuke_old=True)
                else:
                    # Handle the update
                    if vm_state == 'VM_RUNNING':
                        job = self.vmops.update_vm(instance)
                if job:
                    jobs[instance_id] = job
                    tasks[instance_id] = None

            if jobs:
                if [tasks[x] for x in tasks if tasks[x]]:
                    _, tasks = self.vim.update_many_objects(tasks)
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
                        ipv4 = self.instances[instance_id]['ipv4']
                        private = dict(ip=ipv4, dns=ipv4)
                        updated_props[instance_id] = dict(host=ipv4, private=private)
                    except Exception, err:
                        self.log.error("%s failed: %s", instance_id, err)
                        del tasks[instance_id]
                        del jobs[instance_id]
                        error_count += 1

                if time.time() >= next_report:
                    self.log.info("%s instances %r, waiting...", len(updated_props), wait_state)
                    next_report = time.time() + 10.0

                time.sleep(2)

        if error_count:
            raise errors.CloudError("%d jobs failed" % error_count)

        return updated_props

    def create_snapshot(self, props, name=None, description=None, memory=False):
        instances = dict((x['instance'], self._get_instance(x)) for x in props)
        args = dict(name=name, description=description, memory=memory)
        return self.vmops.run_on_instances(instances, self.vmops.create_snapshot, args)

    def revert_to_snapshot(self, props, name=None):
        instances = dict((x['instance'], self._get_instance(x)) for x in props)
        args = dict(name=name, wait_for_ip=False)
        return self.vmops.run_on_instances(instances, self.vmops.revert_to_snapshot, args)

    def remove_snapshot(self, props, name):
        instances = dict((x['instance'], self._get_instance(x)) for x in props)
        args = dict(name=name)
        return self.vmops.run_on_instances(instances, self.vmops.remove_snapshot, args)

    def power_off_instances(self, props):
        instances = dict((x['instance'], self._get_instance(x)) for x in props)
        args = dict(off=True)
        return self.vmops.run_on_instances(instances, self.vmops.power_on_off_vm, args)

    def power_on_instances(self, props):
        instances = dict((x['instance'], self._get_instance(x)) for x in props)
        return self.vmops.run_on_instances(instances, self.vmops.power_on_off_vm)
