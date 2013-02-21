"""
Cloud VM instance operations: creating, querying status, terminating

Copyright (c) 2010-2012 Mika Eloranta
See LICENSE for details.

"""
from . import errors
from . import cloud_aws
from . import cloud_eucalyptus
from . import cloud_libvirt
from . import cloud_vsphere
from .cloudbase import Provider # provides backward compatibility with older extensions


PROVIDERS = {
    "aws-ec2" : cloud_aws.AwsProvider,
    "eucalyptus" : cloud_eucalyptus.EucalyptusProvider,
    "libvirt" : cloud_libvirt.LibvirtProvider,
    "vsphere" : cloud_vsphere.VSphereProvider,
    }


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


