"""
Cloud-provider: base-classes

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""
from . import errors


class NoProviderMethod(NotImplementedError):
    def __init__(self, obj, func):
        name = (obj if isinstance(obj, type) else obj.__class__).__name__
        NotImplementedError.__init__(self, "{0} does not implement {1}".format(name, func))


class Provider(object):
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

    def required_prop(self, cloud_prop, prop_name):
        value = cloud_prop.get(prop_name)
        if value is None:
            raise errors.CloudError("'cloud.{0}' property required by {1} not defined".format(
                    prop_name, self.provider_id))
        return value

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
        raise NoProviderMethod(cls, "get_provider_key")

    def init_instance(self, cloud_prop):
        """
        Create a new instance with the given properties.

        Returns node properties that are changed.
        """
        raise NoProviderMethod(self, "init_instance")

    def assign_ip(self, props):
        """
        Assign the ip's to the instances based on the given properties.
        """
        raise NoProviderMethod(self, "assign_ip")

    def get_instance_status(self, prop):
        """
        Return instance status string for the instance specified in the given
        cloud properties dict.
        """
        raise NoProviderMethod(self, "get_instance_status")

    def terminate_instances(self, props):
        """
        Terminate instances specified in the given sequence of cloud
        properties dicts.
        """
        raise NoProviderMethod(self, "terminate_instances")

    def wait_instances(self, props, wait_state="running"):
        """
        Wait for all the given instances to reach status specified by
        the 'wait_state' argument.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        raise NoProviderMethod(self, "wait_instances")

    def create_snapshot(self, props, name=None, description=None, memory=False):
        """
        Create a new snapshot for the given instances with the specified props.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        raise NoProviderMethod(self, "create_snapshot")

    def revert_to_snapshot(self, props, name=None):
        """
        Revert the given instances to the specified snapshot.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        raise NoProviderMethod(self, "revert_to_snapshot")

    def remove_snapshot(self, props, name):
        """
        Remove the specified snapshot on the given instances.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        raise NoProviderMethod(self, "remove_snapshot")

    def power_off_instances(self, props):
        """
        Power off the given instances.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        raise NoProviderMethod(self, "power_off_instances")

    def power_on_instances(self, props):
        """
        Power on the given instances.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        raise NoProviderMethod(self, "power_on_instances")

    def find_instances(self, match_function):
        """
        Look up instances which have a name matching match_function.

        Returns a list [{vm_name: "vm_name", ...}, ...]
        """
        raise NoProviderMethod(self, "find_instances")
