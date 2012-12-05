"""
Cloud-provider implementation: Amazon AWS EC2

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""
from collections import defaultdict
import copy
import datetime
import logging
import os
import time

from . import errors
from . import cloudbase


BOTO_REQUIREMENT = "2.5.2"
AWS_EC2 = "aws-ec2"
TAG_NAME = "Name"
TAG_PONI_STATE = "PoniState"
TAG_REINIT_RETRY = "PoniReinitRetryCount"
STATE_ASSIGN_EIP = "assign-eip"
STATE_ASSIGNED_EIP = "assigned-eip"
STATE_REINIT = "reinit"
STATE_INITIALIZED = "initialized"
STATE_UNINITIALIZED = "uninitialized"

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


class InstanceStarter(object):
    """Babysit launching of a number of EC2 instances (and/or spot requests)"""
    def __init__(self, provider, props):
        self.log = logging.getLogger(AWS_EC2)
        self.total_instances = len(props)
        self.provider = provider
        self.pending = provider._get_instances(props)
        self.info_by_id = dict((instance.id, dict(start=time.time()))
                               for instance in self.pending
                               if not isinstance(instance, basestring))
        self.props_by_id = dict((p["instance"], p) for p in props)
        self.old_instance_id_by_new_id = dict((instance.id, instance.id) for instance in self.pending)
        self.convert_id_map = {}
        self.output = {}
        self.conn = self.provider._get_conn()

    def check_spot_request_status(self, op):
        """Check spot request status, i.e. if the instance has already been created"""
        spot_req = self.conn.get_all_spot_instance_requests(request_ids=[op])[0]
        if spot_req.fault:
            raise errors.CloudError("AWS spot request failed: %s" %
                                    spot_req.fault)
        if spot_req.state == "active":
            # instance has been created!
            reservations = self.provider.get_all_instances(
                instance_ids=[spot_req.instance_id])
            self.pending.remove(op)

            # start waiting for the instance to boot up
            instance = reservations[0].instances[0]
            self.pending.append(instance)
            self.info_by_id[instance.id] = dict(start=time.time())
            self.props_by_id[instance.id] = self.props_by_id[op]
            self.provider.configure_new_instance(instance, self.props_by_id[op])
            self.convert_id_map[instance.id] = op
        elif spot_req.state == "open":
            # spot request not handled yet, wait some more...
            pass
        else:
            # cancelled or something else
            raise errors.CloudError(
                "Unexpected AWS spot request %s state: '%s'" % (
                    op, spot_req.state))

    def get_output_for_instance(self, instance):
        """Return the correct output dict for the instance"""
        old_instance_id = self.old_instance_id_by_new_id[instance.id]
        return self.output.setdefault(old_instance_id, {})

    def check_instance_status(self, instance, wait_state, check_health):
        """
        Check if the instance has reached desired state.

        Returns True only in the case instance has reached 'running' state
        and the EIP has been successfully attached (when applicable).
        """
        instance.update()

        if (wait_state is None):
            # not waiting for any particular state => DONE
            done = True
        elif instance.state == wait_state:
            # reached the desired state => DONE
            done = True
        else:
            done = False

        check_node_health = check_health and self.props_by_id[instance.id].get("check_health", True)
        if done and check_node_health and not self.provider._instance_status_ok(instance):
            # instance running but has not yet been reported as healthy
            self.log.debug("%s instance running but system or instance status check not ok yet", instance.id)
            done = False

        if not done:
            return False # try again next time

        dns_name = instance.dns_name or instance.private_ip_address
        out_props = self.get_output_for_instance(instance)
        cloud_prop = out_props.setdefault("cloud", self.props_by_id[instance.id].copy())
        cloud_prop["instance"] = instance.id # changed for spot instances
        if "host" not in out_props:
            out_props["host"] = dns_name

        out_props["private"] = dict(
            ip=instance.private_ip_address,
            dns=dns_name)

        eip_mode = cloud_prop.get("eip")
        if eip_mode:
            # Attaching EIP may fail due to inconsistent server-side state at EC2,
            # if the previous owner has recently terminated, so we cannot do it
            # synchronously here. Delegate waiting for the EIP back to the caller.
            if "public" not in out_props:
                instance.add_tag(TAG_PONI_STATE, STATE_ASSIGN_EIP)
                self.log.info("%s: initialized, assigning EIP...", instance.id)
                return False
            else:
                return True
        else:
            if instance in self.pending:
                self.pending.remove(instance)

            return (wait_state == "running")

    def attempt_finalize_eip(self, instance, cloud_prop):
        """Attempt EIP assignment and instance init finalization"""
        try:
            host_eip = self.provider.attach_eip(instance, cloud_prop)
        except boto.exception.EC2ResponseError as error:
            if "is in use" in str(error):
                # EC2 claims the address is still in use, it might take a
                # while to get the address released, retry next time...
                self.log.warning("%s: EIP still in use [%s], waiting...", instance.id, error)
                return
            else:
                raise

        if host_eip:
            # communicate the EIP address properties back to poni
            self.log.info("%s: EIP %s assigned", instance.id, host_eip)
            out_prop = self.get_output_for_instance(instance)
            out_prop["public"] = dict(ip=host_eip, dns=host_eip)
            out_cloud_prop = out_prop.setdefault("cloud", cloud_prop.copy())
            out_cloud_prop["instance"] = instance.id
            if cloud_prop.get("deploy_via_eip"):
                out_prop["host"] = host_eip

        self.pending.remove(instance)
        instance.add_tag(TAG_PONI_STATE, STATE_INITIALIZED)

    @convert_boto_errors
    def wait_instances(self, wait_state="running"):
        while self.pending:
            summary = defaultdict(int)
            for instance in self.pending[:]:
                if isinstance(instance, basestring):
                    summary["spot"] += 1
                    self.check_spot_request_status(instance)
                    continue

                instance.update()
                cloud_prop = self.props_by_id[instance.id]
                prev_retry_count = int(instance.tags.get(TAG_REINIT_RETRY, 0))

                if instance.tags.get(TAG_PONI_STATE) == STATE_ASSIGN_EIP:
                    summary[STATE_ASSIGN_EIP] += 1
                    self.attempt_finalize_eip(instance, cloud_prop)
                else:
                    summary[instance.state] += 1

                if instance.state == "stopped":
                    instance.start()
                    continue
                elif instance.state == "terminated":
                    # instance that had previously failed to start has finally terminated:
                    # create a new instance and try again...
                    out_prop = self.provider._init_instance(cloud_prop, ok_states=["pending", "running"])
                    cloud_prop["instance"] = out_prop["cloud"]["instance"]
                    new_instances = self.provider._get_instances([cloud_prop])
                    new_instance = new_instances[0]

                    # replace old instance with the new one
                    self.pending.append(new_instance)
                    self.pending.remove(instance)
                    self.props_by_id[new_instance.id] = cloud_prop
                    self.provider.configure_new_instance(new_instance, cloud_prop)
                    self.convert_id_map[new_instance.id] = new_instance.id
                    self.old_instance_id_by_new_id[new_instance.id] = instance.id

                    # must also provide some output for the new instance ID
                    self.output[new_instance.id] = self.get_output_for_instance(instance)

                    new_instance.add_tag(TAG_REINIT_RETRY, str(prev_retry_count + 1))
                    self.log.info("instance %s terminated: created new one: %s",
                                  instance.id, new_instance.id)
                    self.info_by_id[new_instance.id] = dict(start=time.time())

                    continue

                # instance exists, check timeout and its state
                # at this point the state is one of: stopping, shutting-down, pending or running
                running_time = time.time() - self.info_by_id[instance.id]["start"]
                default_timeout = float(os.environ.get("PONI_AWS_INIT_TIMEOUT", 300.0))
                start_timeout_seconds = cloud_prop.get("init_timeout", default_timeout)
                if running_time >= start_timeout_seconds:
                    billing_type = cloud_prop.get("billing", "on-demand")
                    if instance.state in ["shutting-down", "stopping"]:
                        raise errors.CloudError(
                            "Instance %s timeout while waiting to exit transient '%s' state" % (
                                instance.id, instance.state))

                    if (wait_state == "running") \
                            and (instance.tags.get(TAG_PONI_STATE) == STATE_UNINITIALIZED) \
                            and (billing_type == "on-demand"):
                        # Attempt to get a healthy instance by destroying this one and creating a new one.
                        # Only on-demand instance creation retry is currently supported.
                        if prev_retry_count > int(os.environ.get("PONI_AWS_INIT_RETRY_COUNT", 2)):
                            raise errors.CloudError(
                                "Failed to get instance %s to healthy state, retries exhausted: %r" % (
                                    instance.id, prev_retry_count))

                        instance.add_tag(TAG_PONI_STATE, STATE_REINIT)
                        instance.terminate()
                        self.info_by_id[instance.id]["start"] = time.time() # reset timer
                        self.log.warning("instance %s took too long to reach healthy state: terminating...",
                                         instance.id)
                        continue # next iterations will re-init it once it has stopped

                    raise errors.CloudError(
                        "Instance %s did not reach healthy running state in time (waited %.1f seconds)" % (
                            instance.id, start_timeout_seconds))

                # instance/system health is only checked if this was a "cloud init"
                check_health = (instance.tags.get(TAG_PONI_STATE) == STATE_UNINITIALIZED)
                if self.check_instance_status(instance, wait_state, check_health=check_health):
                    # instance has reached 'running' state, tag it as initialized
                    instance.add_tag(TAG_PONI_STATE, STATE_INITIALIZED)

            if self.pending:
                self.log.info("[%s/%s] instances ready (%s), waiting...",
                              self.total_instances - len(self.pending), self.total_instances,
                              ", ".join(("%s: %r" % s) for s in summary.iteritems()))
                time.sleep(5.0)

        return self.output


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
        self._spot_req_cache = [] # spot requests created by us during this session
        self._instance_cache = {} # instances created by us during this session

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

    def _find_instance_by_tag(self, tag, value, ok_states=None):
        """
        Find first instance that has been tagged with the specific value.

        The local instance cache that is populated by this session's run_instance
        calls is also looked up in case AWS server-side state is not yet reflecting
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

        # it might also be in the local cache if AWS does not yet return it...
        for instance in self._instance_cache.itervalues():
            instance.update()
            if match(instance):
                return instance

        return None

    def _find_spot_req_by_tag(self, tag, value):
        """Find first active spot request that is tied to this vm_name"""
        for spot_req in self._get_all_spot_requests_plus_cached():
            if spot_req.state in ["open", "active"] and spot_req.tags.get(tag) == value:
                self.log.info("found existing spot req %r for %s=%s: state=%r, tags=%r",
                              spot_req.id, tag, value, spot_req.state, spot_req.tags)
                return spot_req

        return None

    def _get_all_spot_requests_plus_cached(self):
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

    def resolve_subnet_id(self, id_or_name):
        """Return the subnet_id for the given subnet ID or name"""
        conn = self._get_vpc_conn()
        for subnet in conn.get_all_subnets():
            if id_or_name in [subnet.id, subnet.tags.get(TAG_NAME)]:
                return subnet.id

        raise errors.CloudError(
            "subnet with ID or name %r does not exist" % (id_or_name,))

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

    @convert_boto_errors
    def init_instance(self, cloud_prop):
        return self._init_instance(cloud_prop)

    def _init_instance(self, cloud_prop, ok_states=None):
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

        security_groups = cloud_prop.get("security_groups") or []
        if security_groups and isinstance(security_groups, (basestring, unicode)):
            security_groups = [security_groups]
        security_group_ids = [self.get_security_group_id(sg_name)
                              for sg_name in security_groups]

        out_prop = copy.deepcopy(cloud_prop)

        instance = self._find_instance_by_tag(TAG_NAME, vm_name, ok_states=ok_states)
        if instance:
            out_prop["instance"] = instance.id
            return dict(cloud=out_prop)

        spot_req = self._find_spot_req_by_tag(TAG_NAME, vm_name)
        if spot_req:
            # there's already a spot request about this vm_name, return it
            out_prop["instance"] = spot_req.id
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
            "placement": ("placement", str),
            "placement_group": ("placement_group", str),
            "disable_api_termination": ("disable_api_termination", bool),
            "monitoring_enabled": ("monitoring_enabled", bool),
            "subnet_id": ("subnet", self.resolve_subnet_id),
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
                    raise errors.CloudError("invalid AWS cloud property '%s' value %r: %s: %s" % (
                            arg_name, arg_value, error.__class__.__name__, error))

        billing_type = cloud_prop.get("billing", "on-demand")
        if billing_type == "on-demand":
            launch_kwargs["security_group_ids"] = security_group_ids
            instance = self._run_instance(launch_kwargs)
            self.configure_new_instance(instance, cloud_prop)
            out_prop["instance"] = instance.id
        elif billing_type == "spot":
            launch_kwargs["security_groups"] = security_groups
            max_price = cloud_prop.get("spot", {}).get("max_price")
            if not isinstance(max_price, float):
                raise errors.CloudError(
                    "expected float value for cloud.spot.max_price, got '%s'" % (
                        type(max_price)))

            if not max_price:
                raise errors.CloudError("'cloud.spot.max_price' required but not defined")

            spot_reqs = conn.request_spot_instances(max_price, **launch_kwargs)
            spot_reqs[0].add_tag(TAG_NAME, vm_name)
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
                instance.add_tag(TAG_NAME, cloud_prop["vm_name"])
                instance.update()
                if TAG_PONI_STATE not in instance.tags:
                    # only override the tag if one does not already exist, this
                    # guarantees that "uninitialized" instances are safe to destroy
                    # and reinit in case to failed launch attemps
                    instance.add_tag(TAG_PONI_STATE, STATE_UNINITIALIZED)
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
                           " or not found in region '%s': %s: %s",
                           eip, self.region, error.__class__.__name__, error)
            return

        if len(address) == 1:
            address = address[0]
        else:
            self.log.error(
            "The given elastic ip [%r] was not found in region %r",
            eip, self.region)
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
                instance.remove_tag(TAG_NAME)
                instance.remove_tag(TAG_PONI_STATE)
                instance.remove_tag(TAG_REINIT_RETRY)
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

    def _instance_status_ok(self, instance):
        """Return True unless system or instance status check report non-ok"""
        conn = self._get_conn()
        results = conn.get_all_instance_status(instance_ids=[instance.id])
        return (len(results) > 0) and (results[0].system_status.status == "ok") and (results[0].instance_status.status == "ok")

    @convert_boto_errors
    def wait_instances(self, props, wait_state="running"):
        starter = InstanceStarter(self, props)
        return starter.wait_instances(wait_state)
