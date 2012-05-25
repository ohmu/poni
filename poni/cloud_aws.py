"""
Cloud-provider implementation: Amazon AWS EC2

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""
import os
import copy
import time
import logging
from . import errors
from . import cloudbase


BOTO_REQUIREMENT = "2.0"
AWS_EC2 = "aws-ec2"


try:
    import boto
    import boto.ec2
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


class AwsProvider(cloudbase.Provider):
    @classmethod
    def get_provider_key(cls, cloud_prop):
        region = cloud_prop.get("region")
        if not region:
            raise errors.CloudError(
                "'region' property must be set for AWS EC2 instances")

        # ("aws-ec2", region_key) uniquely identifies the DC we are talking to
        return (AWS_EC2, region)

    def __init__(self, cloud_prop):
        assert boto, "boto is not installed, cannot access AWS"
        assert boto.Version >= BOTO_REQUIREMENT, "boto version is too old, cannot access AWS"
        cloudbase.Provider.__init__(self, AWS_EC2, cloud_prop)
        self.log = logging.getLogger(AWS_EC2)
        self.region = cloud_prop["region"]
        self._conn = None

    def _get_conn(self):
        if self._conn:
            return self._conn

        required_env = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
        for env_key in required_env:
            if not os.environ.get(env_key):
                raise errors.CloudError("%r environment variable must be set"
                                        % env_key)

        region = boto.ec2.get_region(self.region)
        if not region:
            raise errors.CloudError("AWS EC2 region %r unknown" % (
                    self.region,))

        self._conn = region.connect()
        return self._conn

    @convert_boto_errors
    def init_instance(self, cloud_prop):
        conn = self._get_conn()
        image_id = cloud_prop.get("image")
        if not image_id:
            raise errors.CloudError(
                "'cloud.image' property required by EC2 not defined")

        vm_name = cloud_prop.get("vm_name")
        if not vm_name:
            raise errors.CloudError(
                "'cloud.vm_name' property required by EC2 not defined")

        images = conn.get_all_images(image_ids=[image_id])
        if not images:
            raise errors.CloudError(
                "AMI with id %r not found in region %r AWS images" % (
                    image_id, self.region))
        elif len(images) > 1:
            raise errors.CloudError(
                "AMI %r seems to match multiple images" % (image_id))

        image = images[0]
        try:
            # renamed setting: backward-compatibility
            key_name = cloud_prop.get("key_pair", cloud_prop.get("key-pair"))
            if not key_name:
                raise KeyError
        except KeyError:
            raise errors.CloudError("'cloud.key_pair' cloud property not set")

        security_groups = cloud_prop.get("security_groups")
        if security_groups and isinstance(security_groups, (basestring, unicode)):
            security_groups = [security_groups]

        reservation = image.run(key_name=key_name,
                                # client_token=vm_name, # guarantees VM creation idempotency, disabled: run() doesn't support this arg
                                kernel_id=cloud_prop.get("kernel"),
                                ramdisk_id=cloud_prop.get("ramdisk"),
                                instance_type=cloud_prop.get("type"),
                                placement=cloud_prop.get("placement"),
                                placement_group=cloud_prop.get("placement_group"),
                                security_groups=security_groups)
        instance = reservation.instances[0]
        instance.add_tag("Name", vm_name) # add a user-frienly name visible in the AWS EC2 console
        out_prop = copy.deepcopy(cloud_prop)
        out_prop["instance"] = instance.id

        return dict(cloud=out_prop)

    @convert_boto_errors
    def assign_ip(self, props):
        conn = self._get_conn()
        for p in props:
            self._assign_ip(conn, p)

    def _assign_ip(self, conn, prop):
        if not "eip" in prop or not "instance" in prop: return
        instances = self._get_instances([prop])
        if not len(instances) or not instances[0].state == "running": return
        instance = instances[0]
        eip = prop["eip"]
        address = None
        try:
            address = conn.get_all_addresses([eip])
        except boto.exception.BotoServerError, error:
            self.log.error(
                "The given elastic ip [%r] was invalid"
                " or not found in region %r" % (
                    eip, self.region)
            )
            self.log.error(repr(error))
            return

        if len(address) == 1:
            address = address[0];
        else:
            self.log.error(
                "The given elastic ip [%r] was not found in region %r" % (
                    eip, self.region))
        if address.instance_id and not address.instance_id == instance.id:
            self.log.error(
                "The given elastic ip [%r] has already"
                " beeen assigned to instance %r" % (
                    eip, address.instance_id))

        if address and not address.instance_id:
            self.log.info("Assigning ip address[%r] to instance[%r]" % (eip, instance.id))
            instance.use_ip(address)
            instance.update()

    def _get_instances(self, props):
        conn = self._get_conn()
        reservations = conn.get_all_instances(instance_ids=[p["instance"]
                                                            for p in props])
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
        for instance in self._get_instances(props):
            instance.terminate()

    @convert_boto_errors
    def wait_instances(self, props, wait_state="running"):
        pending = self._get_instances(props)
        output = {}
        while pending:
            for instance in pending[:]:
                instance.update()
                if (wait_state is None) or (instance.state == wait_state):
                    pending.remove(instance)
                    if wait_state:
                        self.log.debug("%s entered state: %s", instance.id,
                                       wait_state)
                    output[instance.id] = dict(
                        host=instance.dns_name,
                        private=dict(ip=instance.private_ip_address,
                                     dns=instance.private_dns_name))

            if pending:
                self.log.info("[%s/%s] instances %r, waiting...",
                              len(output), len(output) + len(pending),
                              wait_state)
                time.sleep(5)

        return output
