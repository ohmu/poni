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
        self._spot_req_cache = []

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

    def _find_instance_by_tag(self, tag, value):
        """Find first instance that has been tagged with the specific value"""
        reservations = self.get_all_instances()
        for instance in (r.instances[0] for r in reservations):
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
            kernel_id=cloud_prop.get("kernel"),
            ramdisk_id=cloud_prop.get("ramdisk"),
            instance_type=cloud_prop.get("type"),
            placement=cloud_prop.get("placement"),
            placement_group=cloud_prop.get("placement_group"),
            security_groups=security_groups
            )
        billing_type = cloud_prop.get("billing", "on-demand")
        if billing_type == "on-demand":
            reservation = conn.run_instances(
                #client_token=vm_name, # guarantees VM creation idempotency
                **launch_kwargs
                )
            instance = reservation.instances[0]
            # add a user-friendly name visible in the AWS EC2 console
            instance.add_tag("Name", vm_name)
            out_prop["instance"] = instance.id
        elif billing_type == "spot":
            max_price = cloud_prop.get("spot", {}).get("max_price")
            if not isinstance(max_price, float):
                raise errors.CloudError("expected float value for cloud.spot.max_price, got '%s'" % type(max_price))

            if not max_price:
                raise errors.CloudError("cloud.spot.max_price required but not defined")

            spot_reqs = conn.request_spot_instances(max_price, **launch_kwargs)
            spot_reqs[0].add_tag("Name", vm_name)
            out_prop["instance"] = spot_reqs[0].id
            # Workaround the problem that spot request are not immediately visible in
            # full listing...
            self._spot_req_cache.append(spot_reqs[0])
        else:
            raise errors.CloudError("unsupported cloud.billing: %r" % billing_type)

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
        """wrapper to workaround the EC2 bogus 'instance ID ... does not exist' errors"""
        conn = self._get_conn()
        start = time.time()
        while True:
            try:
                return conn.get_all_instances(instance_ids=instance_ids)
            except boto.exception.EC2ResponseError as error:
                if not "does not exist" is str(error):
                    raise

            if (time.time() - start) > 15.0:
                raise errors.CloudError("instances %r did not appear in time" %
                                        instance_ids)

            time.sleep(2.0)

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
                        vm_name = props_by_id[op].get("vm_name")
                        if vm_name:
                            instance.add_tag("Name", vm_name)
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
                    output[old_instance_id] = dict(
                        cloud=cloud_prop,
                        host=instance.dns_name,
                        private=dict(ip=instance.private_ip_address,
                                     dns=instance.private_dns_name))

            if pending:
                self.log.info("[%s/%s] instances %r, waiting...",
                              len(output), len(output) + len(pending),
                              wait_state)
                time.sleep(5)

        return output
