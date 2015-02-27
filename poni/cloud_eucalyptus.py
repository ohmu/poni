"""
Cloud-provider implementation: Eucalyptus

Implement Eucalyptus support by overriding AWS provider connection method.

Copyright (c) 2010-2013 Mika Eloranta
Copyright (c) 2012-2014 F-Secure
See LICENSE for details.

"""
import logging
import os
try:
    from urllib.parse import urlsplit  # pylint: disable=E0611
except ImportError:
    from urlparse import urlsplit

from . import errors

from . import cloud_aws

EUCALYPTUS = "eucalyptus"

try:
    import boto
except ImportError:
    boto = None


class EucalyptusProvider(cloud_aws.AwsProvider):
    @classmethod
    def get_provider_key(cls, cloud_prop):
        endpoint_url = os.environ.get('EC2_URL')
        if not endpoint_url:
            raise errors.CloudError(
                "EC2_URL must be set for Eucalyptus provider")

        # ("eucalyptus", endpoint) uniquely identifies the DC we are talking to
        return (EUCALYPTUS, endpoint_url)

    def __init__(self, cloud_prop):
        # the chain will end up with provider_id set by the AWS module, so we reset it here
        cloud_aws.AwsProvider.__init__(self, cloud_prop)
        self.provider_id = EUCALYPTUS
        self.log = logging.getLogger(EUCALYPTUS)

    def _get_conn(self):
        if self._conn:
            return self._conn

        required_env = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "EC2_URL"]
        for env_key in required_env:
            if not os.environ.get(env_key):
                raise errors.CloudError("%r environment variable must be set"
                                        % env_key)

        try:
            parsed_url = urlsplit(os.environ.get("EC2_URL"))
            host, port = parsed_url.netloc.split(':', 1)  # pylint: disable=E1103
            port = int(port)
        except (ValueError, AttributeError):
            raise errors.CloudError("Failed to parse EC2_URL environmental variable")

        self._conn = boto.connect_euca(aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'], aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
                                       host=host,
                                       port=port,
                                       path=parsed_url.path)  # pylint: disable=E1103
        return self._conn

    def _get_vpc_conn(self):
        raise errors.CloudError("Eucalyptus doesn't support VPCs yet")
