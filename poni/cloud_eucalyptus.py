"""
Cloud-provider implementation: Eucalyptus

Author: Heikki Nousiainen, based on cloud_aws

Copyright (c) 2010-2013 Mika Eloranta
Copyright (c) 2012-2013 F-Secure
See LICENSE for details.

"""
import copy
import logging
import os
import time
import urlparse
from distutils.version import LooseVersion

from . import errors
from . import cloudbase

from . import cloud_aws

BOTO_REQUIREMENT = LooseVersion("2.5.2")
EUCALYPTUS = "eucalyptus"
EUCALYPTUS_API_VERSION = "2013-02-01"

try:
    import boto
    import boto.ec2
    import boto.ec2.blockdevicemapping
    import boto.exception
except ImportError:
    boto = None


class EucalyptusProvider(cloudbase.Provider):
    @classmethod
    def get_provider_key(cls, cloud_prop):
        endpoint_url = os.environ.get('EUCA_URL')
        if not endpoint_url:
            raise errors.CloudError(
                "EUCA_URL must be set for Eucalyptus provider")

        # ("eucalyptus", endpoint) uniquely identifies the DC we are talking to
        return (EUCALYPTUS, endpoint_url)

    def __init__(self, cloud_prop):
        assert boto, "boto is not installed, cannot access Eucalyptus"
        assert LooseVersion(boto.Version) >= BOTO_REQUIREMENT, "boto version is too old, cannot access Eucalyptus"
        cloudbase.Provider.__init__(self, EUCALYPTUS, cloud_prop)
        self.log = logging.getLogger(EUCALYPTUS)
        self._conn = None
        self._instance_cache = {} # instances created by us during this session

    def _get_conn(self):
        if self._conn:
            return self._conn

        required_env = ["EUCA_ACCESS_KEY", "EUCA_SECRET_KEY", "EUCA_URL"]
        for env_key in required_env:
            if not os.environ.get(env_key):
                raise errors.CloudError("%r environment variable must be set"
                                        % env_key)

        try:
            parsed_url = urlparse.urlsplit(os.environ.get("EUCA_URL"))
            host, port = parsed_url.netloc.split(':', 1)
            port = int(port)
        except (ValueError, AttributeError):
            raise errors.CloudError("Failed to parse EUCA_URL environmental variable")

        self._conn = boto.connect_euca(aws_access_key_id=os.environ['EUCA_ACCESS_KEY'], aws_secret_access_key=os.environ['EUCA_SECRET_KEY'],
                                       host=host,
                                       port=port,
                                       path='/services/Eucalyptus',
                                       api_version=EUCALYPTUS_API_VERSION)
        return self._conn

    def _find_instance_by_tag(self, tag, value, ok_states=None):
        """
        Find first instance that has been tagged with the specific value.

        The local instance cache that is populated by this session's run_instance
        calls is also looked up in case server-side state is not yet reflecting
        the very latest created instances.
        """
        ok_states = ok_states or ["running", "pending", "stopping", "shutting-down", "stopped"]
        reservations = self.get_all_instances()
        instances = [r.instances[0] for r in reservations]
        def match(instance):
            return (instance.tags.get(tag) == value) and (ok_states is None or instance.state in ok_states)

        for instance in instances:
            if match(instance):
                return instance

        # it might also be in the local cache if the service does not yet return it...
        for instance in self._instance_cache.itervalues():
            instance.update()
            if match(instance):
                return instance

        return None

    def get_security_group_id(self, group_name):
        conn = self._get_conn()
        groups = [g for g in conn.get_all_security_groups() if g.name == group_name]
        if not groups:
            raise errors.CloudError("security group '%s' does not exist" % group_name)

        return groups[0].id

    def add_extra_tags(self, instance, cloud_prop):
        """Add extra tag values specified by the user to an instance"""
        extra_tags = cloud_prop.get("extra_tags", {})
        if (not isinstance(extra_tags, dict) or
            any((not isinstance(k, basestring) or not isinstance(v, basestring)) for k, v in extra_tags.iteritems())):
            raise errors.CloudError(
                "invalid 'extra_tags' value %r: dict containing str:str mapping required" % (extra_tags,))

        for key, value in extra_tags.iteritems():
            instance.add_tag(key, value)

    def _run_instance(self, launch_kwargs):
        """Launch a new instance and record it in the internal cache"""
        conn = self._get_conn()
        reservation = conn.run_instances(**launch_kwargs)
        instance = reservation.instances[0]
        self._instance_cache[instance.id] = instance
        return instance

    @cloud_aws.convert_boto_errors
    def init_instance(self, cloud_prop):
        return self._init_instance(cloud_prop)

    def _init_instance(self, cloud_prop, ok_states=None):
        conn = self._get_conn()
        image_id = cloud_prop.get("image")
        if not image_id:
            raise errors.CloudError(
                "'cloud.image' property not defined")

        vm_name = cloud_prop.get("vm_name")
        if not vm_name:
            raise errors.CloudError(
                "'cloud.vm_name' property not defined")

        key_name = cloud_prop.get("key_pair")
        if not key_name:
            raise errors.CloudError("'cloud.key_pair' cloud property not set")

        security_groups = cloud_prop.get("security_groups") or []
        if security_groups and isinstance(security_groups, (basestring, unicode)):
            security_groups = [security_groups]
        security_group_ids = [self.get_security_group_id(sg_name)
                              for sg_name in security_groups]

        out_prop = copy.deepcopy(cloud_prop)

        instance = self._find_instance_by_tag(cloud_aws.TAG_NAME, vm_name, ok_states=ok_states)
        if instance:
            out_prop["instance"] = instance.id
            return dict(cloud=out_prop)

        launch_kwargs = dict(
            image_id=image_id,
            key_name=key_name,
            instance_type=cloud_prop.get("type"),
            block_device_map=self.create_disk_map(cloud_prop),
            )

        optional_args = {
            "kernel_id": ("kernel", str),
            "ramdisk_id": ("ramdisk_id", str),
            }
        for arg_name, (key_name, arg_type) in optional_args.iteritems():
            arg_value = cloud_prop.get(key_name)
            if arg_value is not None:
                try:
                    launch_kwargs[arg_name] = arg_type(arg_value)
                except Exception as error:
                    raise errors.CloudError("invalid Eucalyptus cloud property '%s' value %r: %s: %s" % (
                            arg_name, arg_value, error.__class__.__name__, error))

        launch_kwargs["security_group_ids"] = security_group_ids
        instance = self._run_instance(launch_kwargs)
        self.configure_new_instance(instance, cloud_prop)
        out_prop["instance"] = instance.id

        return dict(cloud=out_prop)

    def configure_new_instance(self, instance, cloud_prop):
        """configure the properties, disks, etc. after the instance is running"""
        # add a user-friendly name
        start_time = time.time()
        while True:
            try:
                instance.add_tag(cloud_aws.TAG_NAME, cloud_prop["vm_name"])
                instance.update()
                if cloud_aws.TAG_PONI_STATE not in instance.tags:
                    # only override the tag if one does not already exist, this
                    # guarantees that "uninitialized" instances are safe to destroy
                    # and reinit in case to failed launch attemps
                    instance.add_tag(cloud_aws.TAG_PONI_STATE, cloud_aws.STATE_UNINITIALIZED)
                break
            except boto.exception.EC2ResponseError as error:
                if not "does not exist" in str(error):
                    raise
            if (time.time() - start_time) > 60.0:
                raise errors.CloudError("instance id: %r that we were setting a Name: %r did not appear in time" % (instance.id, cloud_prop["vm_name"]))
            time.sleep(1.0)

        self.add_extra_tags(instance, cloud_prop)

    def create_disk_map(self, cloud_prop):
        """return a boto block_device_map created form the cloud properties"""
        hardware = cloud_prop.get("hardware", {})
        disk_map = boto.ec2.blockdevicemapping.BlockDeviceMapping()
        vm_name = cloud_prop["vm_name"]
        for disk_num in xrange(10):
            disk = hardware.get("disk%d" % disk_num)
            if not disk:
                continue

            try:
                device = disk["device"]
            except KeyError:
                raise errors.CloudError(
                    "%s: required Eucalyptus disk key 'device' (e.g. '/dev/sdh') required"
                    " but not found" % vm_name)

            dev = boto.ec2.blockdevicemapping.BlockDeviceType()
            dev.size = disk['size']
            dev.delete_on_termination = disk.get("delete_on_termination", True)
            if disk.get("snapshot"):
                dev.snapshot_id = disk.get("snapshot")

            self.log.info("%s: device %s type %s", cloud_prop.get("vm_name"), device, disk.get("type"))

            disk_map[device] = dev

        return disk_map

    @cloud_aws.convert_boto_errors
    def assign_ip(self, props):
        conn = self._get_conn()
        for p in props:
            self._assign_ip(conn, p)

    def _assign_ip(self, conn, prop):
        if not "eip" in prop or not "instance" in prop:
            return

        instances = self._get_instances([prop])
        if not len(instances) or not instances[0].state == "running":
            return

        instance = instances[0]
        eip = prop["eip"]
        address = None
        try:
            address = conn.get_all_addresses([eip])
        except boto.exception.BotoServerError, error:
            self.log.error("The given elastic ip [%s] was invalid"
                           " or not found: %s: %s",
                           eip, error.__class__.__name__, error)
            return

        if len(address) == 1:
            address = address[0]
        else:
            self.log.error(
            "The given elastic ip [%r] was not found",
            eip)
        if address.instance_id and not address.instance_id == instance.id:
            self.log.error(
                "The given elastic ip [%r] has already "
                "been assigned to instance %r", eip, address.instance_id)

        if address and not address.instance_id:
            self.log.info("Assigning ip address[%r] to instance[%r]", eip, instance.id)
            instance.use_ip(address)
            instance.update()

    def _get_instances(self, props):
        instance_ids = [p["instance"] for p in props if p["instance"].startswith("i-")]
        reservations = self.get_all_instances(
            instance_ids=instance_ids) if instance_ids else []
        return [r.instances[0] for r in reservations]

    @cloud_aws.convert_boto_errors
    def get_instance_status(self, prop):
        instances = self._get_instances([prop])
        if instances:
            return instances[0].state
        else:
            return None

    @cloud_aws.convert_boto_errors
    def terminate_instances(self, props):
        for instance in self._get_instances(props):
            instance.remove_tag(cloud_aws.TAG_NAME)
            instance.remove_tag(cloud_aws.TAG_PONI_STATE)
            instance.remove_tag(cloud_aws.TAG_REINIT_RETRY)
            instance.terminate()

    def get_all_instances(self, instance_ids=None):
        """Wrapper to workaround the EC2 bogus 'instance ID ... does not exist' errors"""
        conn = self._get_conn()
        start = time.time()
        while True:
            try:
                return conn.get_all_instances(instance_ids=instance_ids)
            except boto.exception.EC2ResponseError as error:
                if not "does not exist" in str(error):
                    raise

            if (time.time() - start) > 15.0:
                raise errors.CloudError("instances %r did not appear in time" %
                                        instance_ids)

            time.sleep(1.0)

    def get_instance_eip(self, instance):
        """Get the attached EIP for the 'instance', if available"""
        conn = self._get_conn()
        for eip in conn.get_all_addresses():
            if eip.instance_id == instance.id:
                return eip

        return None

    def attach_eip(self, instance, cloud_prop):
        """Create and attach an Elastic IP address to the instance"""
        eip_mode = cloud_prop.get("eip")
        if not eip_mode:
            return None

        host_eip = self.get_instance_eip(instance)
        if host_eip:
            return host_eip.public_ip

        if eip_mode == "allocate":
            conn = self._get_conn()
        else:
            # TODO: implement assigning a specific EIP (EIP address given)
            assert False, "'eip' mode %r not supported" % (eip_mode,)

        host_eip = conn.allocate_address()
        host_eip.associate(instance_id=instance.id)

        return host_eip.public_ip

    def _instance_status_ok(self, instance):
        """Return True unless system or instance status check report non-ok"""
        conn = self._get_conn()
        results = conn.get_all_instance_status(instance_ids=[instance.id])
        return (len(results) > 0) and (results[0].system_status.status == "ok") and (results[0].instance_status.status == "ok")

    @cloud_aws.convert_boto_errors
    def wait_instances(self, props, wait_state="running"):
        starter = cloud_aws.InstanceStarter(self, props)
        return starter.wait_instances(wait_state)
