"""
Cloud VM instance operations: creating, querying status, terminating

Copyright (c) 2010-2011 Mika Eloranta
See LICENSE for details.

"""

import os
import copy
import time
import logging
from . import errors

boto_requirement = '2.0'

try:
    import boto
    import boto.ec2
    import boto.exception
except ImportError:
    boto = None


AWS_EC2 = "aws-ec2"


class Sky:
    """Super-cloud provider"""
    def __init__(self):
        self.providers = {}

    def get_provider(self, cloud_prop):
        """
        Return a suitable cloud Provider object for the given cloud properties
        input and specifically the 'provider' type attribute.
        """
        provider_id = cloud_prop.get("provider")
        if not provider_id:
            raise errors.CloudError("cloud 'provider' property not set")

        try:
            provider_class = PROVIDERS[provider_id]
        except KeyError:
            raise errors.CloudError("unknown cloud provider %r" % (
                    provider_id,))

        key = provider_class.get_provider_key(cloud_prop)
        cached = self.providers.get(key)
        if not cached:
            cached = provider_class(cloud_prop)
            self.providers[key] = cached
            return cached

        return cached


class Provider:
    """Abstract base-class for cloud-specific cloud provider logic"""
    def __init__(self, provider_id):
        self.provider_id = provider_id

    @classmethod
    def get_provider_key(cls, cloud_prop):
        """
        Return a cloud Provider object for the given cloud properties.

        A unique provider object can be returned based on, for example, the
        region of the specified data-center.

        Returns a minimum unique key value needed to uniquely describe the
        cloud Provider. Can be e.g. (provider_type, data_center_id), like
        with AWS-EC2.
        """
        assert 0, "implement in sub-class"

    def init_instance(self, cloud_prop):
        """
        Create a new instance with the given properties.

        Returns node properties that are changed.
        """
        assert 0, "implement in sub-class"

    def get_instance_status(self, prop):
        """
        Return instance status string for the instance specified in the given
        cloud properties dict.
        """
        assert 0, "implement in sub-class"

    def terminate_instances(self, props):
        """
        Terminate instances specified in the given sequence of cloud
        properties dicts.
        """
        assert 0, "implement in sub-class"

    def wait_instances(self, props, wait_state="running"):
        """
        Wait for all the given instances to reach status specified by
        the 'wait_state' argument.

        Returns a dict {instance_id: dict(<updated properties>)}
        """


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


class AwsProvider(Provider):
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
        assert boto.Version >= boto_requirement, "boto version is too old, cannot access AWS"
        Provider.__init__(self, AWS_EC2)
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
                "cloud 'image' property required by EC2 not defined")

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
            key_name = cloud_prop["key-pair"]
        except KeyError:
            raise errors.CloudError("'key-pair' cloud property not set")

        reservation = image.run(key_name=key_name,
                                kernel_id=cloud_prop.get("kernel"),
                                ramdisk_id=cloud_prop.get("ramdisk"),
                                instance_type=cloud_prop.get("type"))
        instance = reservation.instances[0]
        out_prop = copy.deepcopy(cloud_prop)
        out_prop["instance"] = instance.id
        return dict(cloud=out_prop)

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


PROVIDERS = {
    "aws-ec2" : AwsProvider,
    }

