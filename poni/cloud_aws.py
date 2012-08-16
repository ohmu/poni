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


BOTO_REQUIREMENT = "2.4.1"
AWS_EC2 = "aws-ec2"


try:
    import boto
    import boto.ec2
    import boto.ec2.blockdevicemapping
    import boto.exception
    import boto.vpc
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
        self._vpc_conn = None
        self._spot_req_cache = []

    def _prepare_conn(self):
        required_env = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
        for env_key in required_env:
            if not os.environ.get(env_key):
                raise errors.CloudError("%r environment variable must be set"
                                        % env_key)

        region = boto.ec2.get_region(self.region)
        if not region:
            raise errors.CloudError("AWS EC2 region %r unknown" % (
                    self.region,))

        return region

    def _get_conn(self):
        if not self._conn:
            region = self._prepare_conn()
            self._conn = region.connect()

        return self._conn

    def _get_vpc_conn(self):
        if not self._vpc_conn:
            region = self._prepare_conn()
            self._vpc_conn = boto.vpc.VPCConnection(region=region)

        return self._vpc_conn

    def _find_instance_by_tag(self, tag, value):
        """Find first instance that has been tagged with the specific value"""
        reservations = self.get_all_instances()
        for instance in (r.instances[0] for r in reservations):
            # TODO: also accepted "stopped" + start stopped boxes
            if instance.state in ["pending", "running"] and instance.tags.get(tag) == value:
                return instance

        return None

    def _find_spot_req_by_tag(self, tag, value):
        """Find first active spot request that is tied to this vm_name"""
        for spot_req in self.get_all_spot_requests_plus_cached():
            if spot_req.state in ["open", "active"] and spot_req.tags.get(tag) == value:
                self.log.info("found existing spot req %r for %s=%s: state=%r, tags=%r",
                              spot_req.id, tag, value, spot_req.state, spot_req.tags)
                return spot_req

        return None

    def get_all_spot_requests_plus_cached(self):
        """
        Query all spot requests plus add internally cached ones that don't necessarily
        yet show up in the full listing. This speeds up spot instance creation
        considerably. Typically spot instance seems to show up in the full listing
        60 seconds after it has been created.
        """
        conn = self._get_conn()
        spot_reqs = conn.get_all_spot_instance_requests()
        spot_reqs.extend(self._spot_req_cache)
        return spot_reqs

    def get_security_group_id(self, group_name):
        conn = self._get_conn()
        # NOTE: VPC security groups cannot be filtered with the 'groupnames' arg, therefore we
        # list them all
        groups = [g for g in conn.get_all_security_groups() if g.name == group_name]
        if not groups:
            raise errors.CloudError("security group '%s' does not exist" % group_name)

        return groups[0].id

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
        security_group_ids = [self.get_security_group_id(sg_name)
                              for sg_name in security_groups]

        out_prop = copy.deepcopy(cloud_prop)

        instance = self._find_instance_by_tag("Name", vm_name)
        if instance:
            # the instance already exists
            out_prop["instance"] = instance.id
            return dict(cloud=out_prop)

        spot_req = self._find_spot_req_by_tag("Name", vm_name)
        if spot_req:
            # there's already a spot request about this vm_name, return it
            out_prop["instance"] = spot_req.id
            return dict(cloud=out_prop)

        launch_kwargs = dict(
            image_id=image_id,
            key_name=key_name,
            instance_type=cloud_prop.get("type"),
            security_group_ids=security_group_ids,
            block_device_map=self.create_disk_map(cloud_prop),
            )

        optional_args = {
            "kernel_id": ("kernel", str),
            "ramdisk_id": ("ramdisk_id", str),
            "placement": ("placement", str),
            "placement_group": ("placement_group", str),
            "disable_api_termination": ("disable_api_termination", bool),
            "monitoring_enabled": ("monitoring_enabled", bool),
            "subnet_id": ("subnet", str),
            "private_ip_address": ("private_ip_address", str),
            "tenancy": ("tenancy", str),
            "instance_profile_name": ("instance_profile_name", str),
            }
        for arg_name, (key_name, arg_type) in optional_args.iteritems():
            arg_value = cloud_prop.get(key_name)
            if arg_value is not None:
                try:
                    launch_kwargs[arg_name] = arg_type(arg_value)
                except Exception as error:
                    raise errors.CloudError("invalid AWS cloud property '%s' value %r, expected value of type '%s'" % (
                            arg_name, arg_value, arg_type))

        billing_type = cloud_prop.get("billing", "on-demand")
        if billing_type == "on-demand":
            reservation = conn.run_instances(
                #client_token=vm_name, # guarantees VM creation idempotency
                **launch_kwargs
                )
            instance = reservation.instances[0]
            self.configure_new_instance(instance, cloud_prop)
            out_prop["instance"] = instance.id
        elif billing_type == "spot":
            max_price = cloud_prop.get("spot", {}).get("max_price")
            if not isinstance(max_price, float):
                raise errors.CloudError(
                    "expected float value for cloud.spot.max_price, got '%s'" % (
                        type(max_price)))

            if not max_price:
                raise errors.CloudError("'cloud.spot.max_price' required but not defined")

            spot_reqs = conn.request_spot_instances(max_price, **launch_kwargs)
            spot_reqs[0].add_tag("Name", vm_name)
            out_prop["instance"] = spot_reqs[0].id
            # Workaround the problem that spot request are not immediately visible in
            # full listing...
            self._spot_req_cache.append(spot_reqs[0])
        else:
            raise errors.CloudError("unsupported cloud.billing: %r" % billing_type)

        return dict(cloud=out_prop)

    def configure_new_instance(self, instance, cloud_prop):
        """configure the properties, disks, etc. after the instance is running"""
        # add a user-friendly name visible in the AWS EC2 console
        start_time = time.time()
        while True:
            try:
                return instance.add_tag("Name", cloud_prop["vm_name"])
            except boto.exception.EC2ResponseError as error:
                if not "does not exist" in str(error):
                    raise
            if (time.time() - start_time) > 60.0:
                raise errors.CloudError("instance id: %r that we were setting a Name: %r did not appear in time" % (instance.id, cloud_prop["vm_name"]))
            time.sleep(1.0)

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
                    "%s: invalid AWS EBS disk size %r, must be 1024 MB or greater" % (
                        vm_name, disk["size"]))

            try:
                device = disk["device"]
            except KeyError:
                raise errors.CloudError(
                    "%s: required AWS disk key 'device' (e.g. '/dev/sdh') required"
                    " but not found" % vm_name)

            dev = boto.ec2.blockdevicemapping.BlockDeviceType()
            dev.size = size_gb
            dev.delete_on_termination = disk.get("delete_on_termination", True)
            if disk.get("snapshot"):
                dev.snapshot_id = disk.get("snapshot")

            disk_map[device] = dev

        return disk_map

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
        instance_ids = [p["instance"] for p in props if p["instance"].startswith("i-")]
        reservations = self.get_all_instances(
            instance_ids=instance_ids) if instance_ids else []
        spot_req_ids = [p["instance"] for p in props if p["instance"].startswith("sir-")]
        return [r.instances[0] for r in reservations] + spot_req_ids

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
            if isinstance(instance, basestring):
                # spot request
                conn.cancel_spot_instance_requests([instance])
            else:
                # VM instance
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
            if instance.subnet_id:
                # an instance is inside a VPC if it has a subnet_id
                conn = self._get_vpc_conn()
                domain = "vpc"
            else:
                # regular EC2 inside (not in a VPC)
                conn = self._get_conn()
                domain = None
        else:
            # TODO: implement assigning a specific EIP (EIP address given)
            assert False, "'eip' mode %r not supported" % (eip_mode,)

        host_eip = conn.allocate_address(domain=domain)
        conn.associate_address(instance_id=instance.id, allocation_id=host_eip.allocation_id)

        return host_eip.public_ip

    @convert_boto_errors
    def wait_instances(self, props, wait_state="running"):
        pending = self._get_instances(props)
        props_by_id = dict((p["instance"], p) for p in props)
        convert_id_map = {}
        output = {}
        conn = self._get_conn()
        while pending:
            for op in pending[:]:
                if isinstance(op, basestring):
                    # this is a spot request id
                    spot_req = conn.get_all_spot_instance_requests(request_ids=[op])[0]
                    if spot_req.fault:
                        raise errors.CloudError("AWS spot request failed: %s" %
                                                spot_req.fault)
                    if spot_req.state == "active":
                        # instance has been created!
                        reservations = self.get_all_instances(
                            instance_ids=[spot_req.instance_id])
                        pending.remove(op)
                        # start waiting for the instance to boot up
                        instance = reservations[0].instances[0]
                        pending.append(instance)
                        props_by_id[instance.id] = props_by_id[op]
                        self.configure_new_instance(instance, props_by_id[op])
                        convert_id_map[instance.id] = op
                    elif spot_req.state == "open":
                        # spot request not handled yet, wait some more...
                        pass
                    else:
                        # cancelled or something else
                        raise errors.CloudError(
                            "Unexpected AWS spot request %s state: '%s'" % (
                                op, spot_req.state))

                    continue

                instance = op
                instance.update()
                if (wait_state is None) or (instance.state == wait_state):
                    pending.remove(instance)
                    if wait_state:
                        self.log.debug("%s entered state: %s", instance.id,
                                       wait_state)

                    cloud_prop = props_by_id[instance.id].copy()
                    cloud_prop["instance"] = instance.id # changed for spot instances
                    old_instance_id = convert_id_map.get(instance.id, instance.id)
                    dns_name = instance.dns_name or instance.private_ip_address
                    out_props = dict(
                        cloud=cloud_prop,
                        host=dns_name,
                        private=dict(
                            ip=instance.private_ip_address,
                            dns=dns_name),
                        )
                    host_eip = self.attach_eip(instance, cloud_prop)
                    if host_eip:
                        out_props["public"] = dict(ip=host_eip, dns=host_eip)
                        if cloud_prop.get("deploy_via_eip"):
                            out_props["host"] = host_eip

                    output[old_instance_id] = out_props

            if pending:
                self.log.info("[%s/%s] instances %r, waiting...",
                              len(output), len(output) + len(pending),
                              wait_state)
                time.sleep(5)

        return output
