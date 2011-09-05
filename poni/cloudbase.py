"""
Cloud-provider: base-classes

Copyright (c) 2010-2011 Mika Eloranta
See LICENSE for details.

"""

from . import errors


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
