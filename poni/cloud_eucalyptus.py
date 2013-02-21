"""
Cloud-provider implementation: Eucalyptus

Author: Heikki Nousiainen, based on cloud_aws

Copyright (c) 2010-2012 Mika Eloranta
Copyright (c) 2012 F-Secure
See LICENSE for details.

"""
from collections import defaultdict
import copy
import logging
import os
import time
import urlparse

from . import errors
from . import cloudbase


BOTO_REQUIREMENT = "2.5.2"
EUCALYPTUS = "eucalyptus"
EUCALYPTUS_API_VERSION = "2009-11-30"


try:
    import boto
    import boto.ec2
    import boto.ec2.blockdevicemapping
    import boto.exception
except ImportError:
    boto = None


def convert_boto_errors(method):
    """Convert remote boto errors to errors.CloudError"""
    def wrapper(self, *args, **kw):
        try:
            return method(self, *args, **kw)
        except boto.exception.BotoServerError, error:
            raise errors.CloudError("%s: %s" % (error.__class__.__name__,
                                                error.error_message))

    wrapper.__doc__ = method.__doc__
    wrapper.__name__ = method.__name__

    return wrapper


class InstanceStarter(object):
    """Babysit launching of a number of Eucalyptus instances"""
    def __init__(self, provider, props):
        self.log = logging.getLogger(EUCALYPTUS)
        self.total_instances = len(props)
        self.provider = provider
        self.pending = provider._get_instances(props)
        self.info_by_id = dict((instance.id, dict(start=time.time()))
                               for instance in self.pending)
        self.props_by_id = dict((p["instance"], p) for p in props)
        self.old_instance_id_by_new_id = dict((instance.id, instance.id) for instance in self.pending)
        self.output = {}
        self.conn = self.provider._get_conn()

    def get_output_for_instance(self, instance):
        """Return the correct output dict for the instance"""
        old_instance_id = self.old_instance_id_by_new_id[instance.id]
        return self.output.setdefault(old_instance_id, {})

    def check_instance_status(self, instance, wait_state):
        """
        Check if the instance has reached desired state.

        Returns True only in the case instance has reached desired state.
        """
        instance.update()

        if (wait_state is None):
            # not waiting for any particular state => DONE
            return True
        elif instance.state != wait_state:
            # has not reached the desired state => DONE
            return False

        out_props = self.get_output_for_instance(instance)
        cloud_prop = out_props.setdefault("cloud", self.props_by_id[instance.id].copy())
        cloud_prop["instance"] = instance.id
        out_props["host"] = instance.public_dns_name

        out_props["private"] = dict(
            ip=instance.private_ip_address,
            dns=instance.private_dns_name)

        return True

    @convert_boto_errors
    def wait_instances(self, wait_state="running"):
        while self.pending:
            summary = defaultdict(int)
            for instance in self.pending[:]:
                instance.update()
                cloud_prop = self.props_by_id[instance.id]

                summary[instance.state] += 1

                if self.check_instance_status(instance, wait_state):
                    self.pending.remove(instance)
                    if wait_state:
                        self.log.debug("%s in state: %s", instance.id,
                                       wait_state)
                    self.output[instance.id] = self.get_output_for_instance(instance)

                if wait_state == "running" and instance.state == "stopped":
                    instance.start()
                    continue
                elif wait_state == "running" and instance.state == "terminated":
                    # instance that had previously failed to start has finally terminated:
                    # create a new instance and try again...
                    out_prop = self.provider._init_instance(cloud_prop)
                    cloud_prop["instance"] = out_prop["cloud"]["instance"]
                    new_instances = self.provider._get_instances([cloud_prop])
                    new_instance = new_instances[0]

                    # replace old instance with the new one
                    self.pending.append(new_instance)
                    self.pending.remove(instance)
                    self.props_by_id[new_instance.id] = cloud_prop
                    self.old_instance_id_by_new_id[new_instance.id] = instance.id

                    # must also provide some output for the new instance ID
                    self.output[new_instance.id] = self.get_output_for_instance(instance)

                    self.log.info("instance %s terminated: created new one: %s",
                                  instance.id, new_instance.id)
                    self.info_by_id[new_instance.id] = dict(start=time.time())

                    continue
                elif wait_state == "running":
                    running_time = time.time() - self.info_by_id[instance.id]["start"]
                    default_timeout = float(os.environ.get("PONI_EUCALYPTUS_INIT_TIMEOUT", 300.0))
                    start_timeout_seconds = cloud_prop.get("init_timeout", default_timeout)
                    if running_time >= start_timeout_seconds:
                        if instance.state in ["shutting-down", "stopping"]:
                            raise errors.CloudError(
                                "Instance %s timeout while waiting to exit transient '%s' state" % (
                                    instance.id, instance.state))

                        # Attempt to get a healthy instance by destroying this one and creating a new one.
                        instance.terminate()
                        self.info_by_id[instance.id]["start"] = time.time() # reset timer
                        self.log.warning("instance %s took too long to reach healthy state: terminating...",
                                         instance.id)
                        continue # next iterations will re-init it once it has stopped

            if self.pending:
                self.log.info("[%s/%s] instances ready (%s), waiting...",
                              self.total_instances - len(self.pending), self.total_instances,
                              ", ".join(("%s: %r" % s) for s in summary.iteritems()))
                time.sleep(5.0)

        return self.output


class EucalyptusProvider(cloudbase.Provider):
    @classmethod
    def get_provider_key(cls, cloud_prop):
        endpoint_url = os.environ.get('EUCA_URL')
        if not endpoint_url:
            raise errors.CloudError(
                "EUCA_URL must be set for Eucalyptus instances")

        # ("eucalyptus", endpoint) uniquely identifies the DC we are talking to
        return (EUCALYPTUS, endpoint_url)

    def __init__(self, cloud_prop):
        assert boto, "boto is not installed, cannot access Eucalyptus"
        assert boto.Version >= BOTO_REQUIREMENT, "boto version is too old, cannot access Eucalyptus"
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

    def get_security_group_id(self, group_name):
        conn = self._get_conn()
        groups = [g for g in conn.get_all_security_groups() if g.name == group_name]
        if not groups:
            raise errors.CloudError("security group '%s' does not exist" % group_name)

        return groups[0].id

    def _run_instance(self, launch_kwargs):
        """Launch a new instance and record it in the internal cache"""
        conn = self._get_conn()
        reservation = conn.run_instances(**launch_kwargs)
        instance = reservation.instances[0]
        self._instance_cache[instance.id] = instance
        return instance

    @convert_boto_errors
    def init_instance(self, cloud_prop):
        return self._init_instance(cloud_prop)

    def _init_instance(self, cloud_prop):
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
        out_prop["instance"] = instance.id

        return dict(cloud=out_prop)

    def create_disk_map(self, cloud_prop):
        """return a boto block_device_map created form the cloud properties"""
        hardware = cloud_prop.get("hardware", {})
        disk_map = boto.ec2.blockdevicemapping.BlockDeviceMapping()
        vm_name = cloud_prop["vm_name"]
        for disk_num in xrange(10):
            disk = hardware.get("disk%d" % disk_num)
            if not disk:
                continue

            size_gb = int(disk["size"] / 1024) # disk size property definitions are in MB
            if size_gb <= 0:
                raise errors.CloudError(
                    "%s: invalid Eucalyptus EBS disk size %r, must be 1024 MB or greater" % (
                        vm_name, disk["size"]))

            try:
                device = disk["device"]
            except KeyError:
                raise errors.CloudError(
                    "%s: required Eucalyptus disk key 'device' (e.g. '/dev/sdh') required"
                    " but not found" % vm_name)

            dev = boto.ec2.blockdevicemapping.BlockDeviceType()
            dev.size = size_gb
            dev.delete_on_termination = disk.get("delete_on_termination", True)
            if disk.get("snapshot"):
                dev.snapshot_id = disk.get("snapshot")

            disk_map[device] = dev

        return disk_map

    def assign_ip(self, props):
        # Not implemented for Eucalyptus
        return

    def _get_instances(self, props):
        instance_ids = [p["instance"] for p in props if p["instance"].startswith("i-")]
        reservations = self.get_all_instances(
            instance_ids=instance_ids) if instance_ids else []
        return [r.instances[0] for r in reservations]

    @convert_boto_errors
    def get_instance_status(self, prop):
        instances = self._get_instances([prop])
        if instances:
            return instances[0].state
        else:
            return None

    @convert_boto_errors
    def terminate_instances(self, props):
        conn = self._get_conn()
        for instance in self._get_instances(props):
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

    @convert_boto_errors
    def wait_instances(self, props, wait_state="running"):
        starter = InstanceStarter(self, props)
        return starter.wait_instances(wait_state)
