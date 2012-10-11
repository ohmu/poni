"""
Cloud-provider: base-classes

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""

class Provider:
    """Abstract base-class for cloud-specific cloud provider logic"""
    def __init__(self, provider_id, cloud_prop):
        self.provider_id = provider_id
        self._provider_key = self.get_provider_key(cloud_prop)

    def __eq__(self, other):
        if not other or not isinstance(other, Provider):
            return False
        return self._provider_key == other._provider_key

    def __ne__(self, other):
        if not other or not isinstance(other, Provider):
            return True
        return self._provider_key != other._provider_key

    def __hash__(self):
        # shuffle the hash a bit to create unique hashes for Provider objects
        # and their provider_keys
        return hash(("cloudbase.Provider", self._provider_key))

    @classmethod
    def get_provider_key(cls, cloud_prop):
        """
        Return the cloud provider key for the given cloud properties.

        A unique provider key can be returned based on, for example, the
        region of the specified data-center.

        Returns a minimum unique key value needed to uniquely describe the
        cloud Provider. Can be e.g. (provider_type, data_center_id), like
        with AWS-EC2. The return value also needs to be hash()able.
        """
        assert 0, "implement in sub-class"

    def init_instance(self, cloud_prop):
        """
        Create a new instance with the given properties.

        Returns node properties that are changed.
        """
        assert 0, "implement in sub-class"

    def assign_ip(self, props):
        """
        Assign the ip's to the instances based on the given properties.
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
        assert 0, "implement in sub-class"

    def create_snapshot(self, props, name=None, description=None, memory=False):
        """
        Create a new snapshot for the given instances with the specified props.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        assert 0, "implement in sub-class"

    def revert_to_snapshot(self, props, name=None):
        """
        Revert the given instances to the specified snapshot.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        assert 0, "implement in sub-class"

    def remove_snapshot(self, props, name):
        """
        Remove the specified snapshot on the given instances.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        assert 0, "implement in sub-class"

    def power_off_instances(self, props):
        """
        Power off the given instances.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        assert 0, "implement in sub-class"

    def power_on_instances(self, props):
        """
        Power on the given instances.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        assert 0, "implement in sub-class"
