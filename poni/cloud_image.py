"""
Cloud-provider implementation: Image builder

Copyright (c) 2014 F-Secure Corporation
See LICENSE for details.

"""
from . import cloudbase
import copy
import logging


class ImageProvider(cloudbase.Provider):
    def __init__(self, cloud_prop):
        cloudbase.Provider.__init__(self, 'image', cloud_prop)
        self.log = logging.getLogger('poni.image')

    @classmethod
    def get_provider_key(cls, cloud_prop):
        """
        Return a cloud Provider object for the given cloud properties.
        """
        return ("image",)

    def init_instance(self, cloud_prop):
        """
        Create a new instance with the given properties.

        Returns node properties that are changed.
        """
        return self._updated_prop(cloud_prop)

    def _updated_prop(self, cloud_prop):
        ip = cloud_prop.get("dummy_ip", "127.255.255.255")
        vm_name = cloud_prop["vm_name"]
        out_prop = dict(cloud=copy.deepcopy(cloud_prop),
                        host=vm_name, private=dict(ip=ip, dns=ip))
        out_prop["cloud"]["instance"] = vm_name
        return out_prop

    def get_instance_status(self, prop):
        """
        Return instance status string for the instance specified in the given
        cloud properties dict.
        """
        return "stopped"

    def terminate_instances(self, props):
        """
        Terminate instances specified in the given sequence of cloud
        properties dicts.
        """
        return

    def wait_instances(self, props, wait_state="running"):
        """
        Wait for all the given instances to reach status specified by
        the 'wait_state' argument.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        return dict((prop["instance"], self._updated_prop(prop)) for prop in props)
