"""
Cloud-provider implementation: Docker

Copyright (c) 2014 F-Secure Corporation
See LICENSE for details.

"""
from . import cloudbase
from . import errors
import copy
import logging
import os
import time

try:
    import docker
    import docker.errors
except ImportError:
    docker = None


def convert_docker_errors(method):
    """Convert docker errors to errors.CloudError"""
    def wrapper(self, *args, **kw):
        try:
            return method(self, *args, **kw)
        except docker.errors.APIError as error:
            raise errors.CloudError("%s: %s" % (error.__class__.__name__, error))

    wrapper.__doc__ = method.__doc__
    wrapper.__name__ = method.__name__

    return wrapper


class DockerProvider(cloudbase.Provider):
    def __init__(self, cloud_prop):
        assert docker, "docker-py is not installed, cannot access docker"
        cloudbase.Provider.__init__(self, 'docker', cloud_prop)
        self.log = logging.getLogger('poni.docker')
        self.base_url = cloud_prop.get("base_url") or os.environ.get('DOCKER_BASE_URL', 'unix://var/run/docker.sock')
        self._conn = None

    @classmethod
    def get_provider_key(cls, cloud_prop):
        """
        Return a cloud Provider object for the given cloud properties.
        """
        return ("docker", cloud_prop.get("base_url"))

    def _get_conn(self, cloud_prop):
        if not self._conn:
            # NOTE: version 1.10 is required for 'dns' setting to work
            self._conn = docker.Client(base_url=self.base_url, version="1.10", timeout=10)

        return self._conn

    def _find_container(self, cloud_prop):
        conn = self._get_conn(cloud_prop)
        c_name = "/" + cloud_prop["vm_name"]
        for prop in conn.containers(all=True):
            if c_name in (prop.get("Names") or []):
                return prop["Id"]
        return None

    @convert_docker_errors
    def init_instance(self, cloud_prop):
        """
        Create a new instance with the given properties.

        Returns node properties that are changed.
        """
        vm_name = self.required_prop(cloud_prop, "vm_name")
        image = self.required_prop(cloud_prop, "image")
        conn = self._get_conn(cloud_prop)
        container_id = self._find_container(cloud_prop)
        binds = cloud_prop.get("binds")
        dns = cloud_prop.get("dns")
        if not container_id:
            prop = conn.create_container(
                image, hostname=vm_name, name=vm_name,
                volumes=binds.keys() if binds else None,
                environment=dict(container="docker"))
            container_id = prop['Id']

        conn.start(container_id, privileged=cloud_prop.get("privileged", False),
                   binds=binds, dns=dns)
        return self._updated_prop(cloud_prop, container_id)

    def _updated_prop(self, cloud_prop, container_id=None):
        conn = self._get_conn(cloud_prop)
        container_id = container_id or cloud_prop["instance"]
        cont_prop = conn.inspect_container(container_id)
        ip = cont_prop["NetworkSettings"]["IPAddress"]
        out_prop = dict(cloud=copy.deepcopy(cloud_prop),
                        host=ip, private=dict(ip=ip, dns=ip))
        out_prop["cloud"]["instance"] = container_id
        return out_prop

    @convert_docker_errors
    def get_instance_status(self, prop):
        """
        Return instance status string for the instance specified in the given
        cloud properties dict.
        """
        conn = self._get_conn(prop)
        cont_prop = conn.inspect_container(prop["instance"])
        if cont_prop["State"]["Paused"]:
            return "paused"
        elif cont_prop["State"]["Running"]:
            return "running"
        else:
            return "stopped"

    @convert_docker_errors
    def terminate_instances(self, props):
        """
        Terminate instances specified in the given sequence of cloud
        properties dicts.
        """
        for prop in props:
            conn = self._get_conn(prop)
            conn.kill(prop["instance"])
            conn.remove_container(prop["instance"])

    @convert_docker_errors
    def wait_instances(self, props, wait_state="running"):
        """
        Wait for all the given instances to reach status specified by
        the 'wait_state' argument.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        out = {}
        for prop in props:
            conn = self._get_conn(prop)
            cont_prop = conn.inspect_container(prop["instance"])
            if wait_state == "running" and cont_prop["State"]["Running"]:
                out[prop["instance"]] = self._updated_prop(prop)
                continue

            time.sleep(1.0)

        return out
