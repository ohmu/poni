"""
LibVirt provider for Poni.
Copyright (C) 2011 F-Secure Corporation, Helsinki, Finland.
Author: Oskari Saarenmaa <ext-oskari.saarenmaa@f-secure.com>
"""

import copy
import datetime
import getpass
import hashlib
import json
import logging
import os
import paramiko
import re
import socket
import subprocess
import time
import uuid
from xml.dom.minidom import parseString as xmlparse

import libvirt
from poni.cloudbase import Provider
from poni.errors import CloudError


if getattr(paramiko.SSHClient, "connect_socket", None):
    SshClientLVP = paramiko.SSHClient
else:
    class SSHClientLVP(paramiko.SSHClient):
        def connect_socket(self, sock, username, key_filename):
            self._transport = paramiko.Transport(sock)
            if self._log_channel is not None:
                self._transport.set_log_channel(self._log_channel)
            self._transport.start_client()
            paramiko.resource.ResourceManager.register(self, self._transport) # pylint: disable=E1120
            self._auth(username or getpass.getuser(), None, None, [key_filename], False, False)

class LVPError(CloudError):
    """LibvirtProvider error"""

class LibvirtProvider(Provider):
    def __init__(self, cloud_prop):
        Provider.__init__(self, self.get_provider_key(cloud_prop), cloud_prop)
        self.log = logging.getLogger("poni.libvirt")
        self.hosts = []
        self.hosts_online = None
        self.instances = {}
        self.ssh_key = None
        profile = json.load(open(cloud_prop["profile"], "rb"))
        if "ssh_key" in profile:
            self.ssh_key = os.path.expandvars(os.path.expanduser(profile["ssh_key"]))
        for host in profile["nodes"]:
            self.hosts.append(PoniLVConn(host, keyfile = self.ssh_key))

    @classmethod
    def get_provider_key(cls, cloud_prop):
        """
        Return a cloud Provider object for the given cloud properties.
        """
        return "PONILV"

    @property
    def conns(self):
        if not self.hosts_online:
            if libvirt.getVersion() < 9004:
                # libvirt support for no_verify was introduced in 0.9.4
                procs = []
                for conn in self.hosts:
                    args = ["/usr/bin/ssh", "-oBatchMode=yes", "-oStrictHostKeyChecking=no",
                            "root@%s" % (conn.host, ), "uptime"]
                    procs.append(subprocess.Popen(args))
                [proc.wait() for proc in procs]

            self.hosts_online = []
            for conn in self.hosts:
                try:
                    conn.connect()
                    self.hosts_online.append(conn)
                except libvirt.libvirtError, ex:
                    self.log.warn("Connection to %r failed: %r", conn.uri, ex)
            if not self.hosts_online:
                raise LVPError("Could not connect to any libvirt host")
        return self.hosts_online

    def __get_instance(self, prop):
        vm_name = instance_id = prop.get('vm_name', None)
        assert vm_name, "vm_name must be specified for libvirt instances"
        source_image = prop.get('source_image', None)
        assert source_image, "source_image must be specified for libvirt instances"
        instance = self.instances.get(instance_id)
        if not instance:
            vm_conns = []
            vm_state = 'VM_NON_EXISTENT'
            for conn in self.conns:
                if vm_name in conn.vms:
                    vm_state = 'VM_DIRTY'
                    vm_conns.append(conn)
            instance = dict(id=instance_id,
                            vm_name=vm_name,
                            vm_state=vm_state,
                            vm_conns=vm_conns)
            self.instances[instance_id] = instance
        return instance

    def init_instance(self, prop):
        """
        Create a new instance with the given properties.

        Returns node properties that are changed.
        """
        instance = self.__get_instance(prop)
        out_prop = copy.deepcopy(prop)
        out_prop["instance"] = instance['id']
        return dict(cloud=out_prop)

    def wait_instances(self, props, wait_state="running"):
        """
        Wait for all the given instances to reach status specified by
        the 'wait_state' argument.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        assert wait_state == "running", "libvirt only handles running stuff"
        result = {}
        home = os.environ.get("HOME")
        for prop in props:
            instance_id = prop['instance']
            instance = self.__get_instance(prop)
            vm_state = instance['vm_state']
            pool = prop.get("storage_pool", "default")
            ipv6pre = prop.get("ipv6_prefix")

            if vm_state in ("VM_DIRTY", "VM_NON_EXISTENT"):
                # Delete any existing instances
                [conn.delete_vm(instance["vm_name"]) for conn in instance["vm_conns"]]
                # Select the best place for this host
                nodes = sorted((conn.weight, conn) for conn in self.conns)
                conn = nodes[-1][1]
            elif vm_state == "VM_RUNNING":
                continue
            else:
                continue # XXX: throw an error?
            instance["vm_conns"] = [conn]
            vm = conn.clone_vm(instance["vm_name"], pool, prop, overwrite = True)
            ipv6_addr = vm.ipv6_addr(ipv6pre)[0]
            self.instances[instance_id]['ipproto'] = prop.get("ipproto", "ipv4")
            self.instances[instance_id]['ipv6'] = ipv6_addr
            self.instances[instance_id]["vm_state"] = "VM_RUNNING"
            ssh_key_path = "%s/.ssh/%s" % (home, prop["ssh_key"])
            self.instances[instance_id]["ssh_key"] = ssh_key_path

        # get ipv4 addresses for the hosts (XXX: come up with something better)
        tunnels = {}
        failed = []
        tries = 0
        objs = []
        start = time.time()

        while (tries == 0) or failed:
            tries += 1
            if tries > 10:
                raise LVPError("Connecting to %r failed" % (failed, ))

            self.log.info("getting ip addresses: round #%r, time spent=%.02fs", tries, (time.time() - start))
            if failed:
                time.sleep(2)
                failed = []

            for instance_id, instance in self.instances.iteritems():
                if instance["ipproto"] in instance:
                    # address already exists (ie lookup done or we're using ipv6)
                    if instance_id not in result:
                        addr = instance[instance['ipproto']]
                        result[instance_id] = dict(host=addr, private=dict(ip=addr, dns=addr))
                    continue

                conn = instance["vm_conns"][0]
                if conn not in tunnels:
                    client = SSHClientLVP()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    client.connect(conn.host, username = conn.username, key_filename = conn.keyfile)
                    tunnels[conn] = client
                trans = tunnels[conn].get_transport()

                ipv4 = None
                try:
                    tunchan = trans.open_channel("direct-tcpip", (instance["ipv6"], 22), ("localhost", 0))
                    client = SSHClientLVP()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    client.connect_socket(tunchan, username = "root", key_filename = instance["ssh_key"])
                    cmdchan = client.get_transport().open_session()
                    cmdchan.set_combine_stderr(True)
                    cmdchan.exec_command('ip -4 addr show scope global')
                    cmdchan.shutdown_write()
                    data = cmdchan.recv(1024)
                    objs.extend((tunchan, cmdchan, client))
                except (socket.error, paramiko.SSHException), ex:
                    self.log.warning("connecting to %r failed: %r", instance, ex)
                else:
                    if data:
                        ipv4 = data.partition(" inet ")[2].partition("/")[0]

                if not ipv4:
                    failed.append(instance)
                else:
                    self.log.info("Got address %r for %r", ipv4, instance)
                    instance['ipv4'] = ipv4
                    addr = instance[instance['ipproto']]
                    result[instance_id] = dict(host=addr, private=dict(ip=addr, dns=addr))

        [client.close() for client in tunnels.itervalues()]
        return result


class PoniLVConn(object):
    def __init__(self, host, uri=None, keyfile=None):
        if not uri:
            uri = "qemu+ssh://root@{0}/system?no_tty=1&no_verify=1&keyfile={1}".\
                  format(host, keyfile or "")
        m = re.search("://(.+?)@", uri)
        self.username = m and m.group(1)
        self.keyfile = keyfile
        self.host = host
        self.uri = uri
        self.conn = None
        self.vms = None
        self.vms_online = 0
        self.vms_offline = 0
        self.cpus_online = 0
        self.pools = None
        self.node = None

    def __repr__(self):
        return "PoniLVConn(%r)" % (self.host)

    @property
    def weight(self):
        online = float((self.vms_online + self.cpus_online / 4) or 1)
        return self.node["total_mhz"] / online

    def connect(self, uri = None):
        self.conn = libvirt.open(uri or self.uri)
        self.refresh_list()
        self.refresh_node()

    def refresh_node(self):
        assert self.conn, "not connected"
        keys = ("cpu", "memory", "cpus", "mhz", "nodes", "sockets", "cores", "threads")
        info = self.conn.getInfo()
        node = dict(zip(keys, info))
        node["total_mhz"] = node["sockets"] * node["cores"] * node["mhz"]
        self.node = node

    def refresh_list(self):
        try:
            self.__refresh_list()
        except libvirt.libvirtError, ex:
            if "Domain not found" not in str(ex):
                raise
            # retry
            self.__refresh_list()

    def __refresh_list(self):
        assert self.conn, "not connected"
        self.vms = {}
        self.vms_online = 0
        self.vms_offline = 0
        for dom_id in self.conn.listDomainsID():
            dom = PoniLVDom(self, self.conn.lookupByID(dom_id))
            self.vms[dom.name] = dom
            self.vms_online += 1
        for name in self.conn.listDefinedDomains():
            dom = PoniLVDom(self, self.conn.lookupByName(name))
            self.vms[dom.name] = dom
            self.vms_offline += 1
        self.pools = {}
        for name in self.conn.listStoragePools():
            pool = PoniLVPool(self.conn.storagePoolLookupByName(name))
            self.pools[name] = pool
        self.cpus_online = sum(dom.info["cpus"] for dom in self.vms.itervalues() if dom.info["cputime"] > 0)

    def delete_vm(self, vm_name):
        if vm_name not in self.vms:
            raise LVPError("%r is not defined" % (vm_name, ))
        self.vms[vm_name].delete()
        self.refresh_list()

    def clone_vm(self, name, pool, spec, overwrite = False):
        desc = """
            <domain type='kvm'>
              <name>%(name)s</name>
              <description>%(desc)s</description>
              <uuid>%(uuid)s</uuid>
              <memory>%(hardware.ram)s</memory>
              <vcpu>%(hardware.cpus)s</vcpu>
              <os>
                <type arch='%(hardware.arch)s' machine='pc'>hvm</type>
                <boot dev='hd'/>
              </os>
              <features>
                <acpi/>
                <apic/>
                <pae/>
              </features>
              <clock offset='utc'/>
              <on_poweroff>destroy</on_poweroff>
              <on_reboot>restart</on_reboot>
              <on_crash>restart</on_crash>
              <devices>
                <disk type='file' device='disk'>
                  <driver name='qemu' type='qcow2' cache='%(hardware.diskcache)s'/>
                  <source file='%(disk_path)s'/>
                  <target dev='vda' bus='virtio'/>
                  <alias name='virtio-disk0'/>
                </disk>
                %(interfaces)s
                <serial type='pty'>
                  <target port='0'/>
                  <alias name='serial0'/>
                </serial>
                <console type='pty'>
                  <target type='serial' port='0'/>
                  <alias name='serial0'/>
                </console>
                <input type='tablet' bus='usb'>
                  <alias name='input0'/>
                </input>
                <input type='mouse' bus='ps2'/>
                <graphics type='vnc' autoport='yes'/>
                <video>
                  <model type='cirrus' vram='9216' heads='1'/>
                  <alias name='video0'/>
                </video>
                <memballoon model='virtio'>
                  <alias name='balloon0'/>
                </memballoon>
              </devices>
            </domain>
            """
        interface_desc = """
                <interface type='%(type)s'>
                  <model type='virtio'/>
                  <mac address='%(mac)s'/>
                  <source %(type)s='%(network)s'/>
                </interface>
                """
        spec = copy.deepcopy(spec)
        default_network = spec.get("default_network", "default")
        def macaddr(index):
            # NOTE: mac address is based on name to have predictable DHCP addresses
            mac_ext = hashlib.md5(name).hexdigest()
            return "52:54:00:%s:%s:%02x" % (mac_ext[0:2], mac_ext[2:4], int(mac_ext[4:6], 16)^index)

        if name in self.vms:
            if not overwrite:
                raise LVPError("%r vm already exists" % (name, ))
            self.delete_vm(name)
        if pool not in self.pools:
            raise LVPError("%r storage does not exist" % (pool, ))
        spec["name"] = name
        if "source_image" not in spec:
            raise LVPError("source_image must be specified")
        if "desc" not in spec:
            spec["desc"] = "created by poni.cloud_libvirt by {0}@{1} on {2}+00:00".format(
                os.getenv("USER"), socket.gethostname(), datetime.datetime.utcnow().isoformat()[0:19])
        if "uuid" not in spec:
            spec["uuid"] = str(uuid.uuid4())
        if isinstance(spec.get("hardware"), dict):
            for k, v in spec["hardware"].iteritems():
                spec["hardware.%s" % (k, )] = v
        if "hardware.arch" not in spec:
            spec["hardware.arch"] = "x86_64"
        if "hardware.ram" not in spec:
            spec["hardware.ram"] = 1024 * 1024
        else:
            spec["hardware.ram"] *= 1024 # convert MB to kB
        if "hardware.cpus" not in spec:
            spec["hardware.cpus"] = 1
        if "hardware.disk" not in spec:
            spec["hardware.disk"] = 8192
        if "hardware.diskcache" not in spec:
            spec["hardware.diskcache"] = "default"
        # Set up interfaces - any hardware.nicX entries in spec,
        # failing that create one interface by default.
        spec["interfaces"] = ""
        nspecs = []
        for i in xrange(100):
            nspec = spec.get("hardware.nic%d" % i)
            if not isinstance(nspec, dict):
                break
            nspecs.append(nspec)
        if not nspecs:
            nspecs.append({})
        for i, nspec in enumerate(nspecs):
            ispec = {
                "mac": nspec.get("mac", macaddr(i)),
                "type": nspec.get("type", "network"),
                "network": nspec.get("network", default_network),
            }
            if "bridge" in nspec: # support for old style bridge-only defs
                ispec["type"] = "bridge"
                ispec["network"] = nspec["bridge"]
            spec["interfaces"] += interface_desc % ispec
        vol = self.pools[pool].clone_volume(spec["source_image"], name, spec["hardware.disk"])
        vol_path = vol.path()
        spec["disk_path"] = vol_path
        new_desc = desc % spec
        vm = self.conn.defineXML(new_desc)
        vm.create()
        self.refresh_list()
        return self.vms[name]


class PoniLVPool(object):
    def __init__(self, pool):
        self.pool = pool
        self.path = None
        self.__read_desc()

    def clone_volume(self, source, target, megabytes):
        desc = """
            <volume>
                <name>auto.%(name)s.qcow2</name>
                <capacity unit="M">%(megabytes)s</capacity>
                <target>
                    <format type='qcow2'/>
                </target>
                <backingStore>
                    <format type='qcow2'/>
                    <path>%(poolpath)s/%(source)s</path>
                </backingStore>
            </volume>
            """
        new_desc = desc % dict(name = target, megabytes = megabytes, source = source, poolpath = self.path)
        return self.pool.createXML(new_desc, 0)

    def __read_desc(self):
        xml = self.pool.XMLDesc(0)
        tree = xmlparse(xml)
        pools = tree.getElementsByTagName("pool")
        if pools:
            targets = pools[0].getElementsByTagName("target")
            if targets:
                paths = targets[0].getElementsByTagName("path")
                if paths:
                    self.path = str(paths[0].firstChild.wholeText)


class PoniLVDom(object):
    def __init__(self, conn, dom):
        self.conn = conn
        self.dom = dom
        self.name = dom.name()
        self.macs = []
        self.disks = []
        self.info = {}
        self.__dom_info()
        self.__read_desc()

    def ipv6_addr(self, prefix = "fe80::"):
        return [mac_to_ipv6(prefix, mac) for mac in self.macs]

    def delete(self):
        try:
            self.dom.destroy()
        except libvirt.libvirtError, ex:
            if "domain is not running" not in str(ex):
                raise

        # lookup and delete storage
        for disk in self.disks:
            delete_ok = False
            delete_ex = []
            try:
                vol = self.conn.conn.storageVolLookupByPath(disk)
                vol.delete(0)
            except libvirt.libvirtError, ex:
                if not "Storage volume not found" in str(ex):
                    raise LVPError("%r: deletion failed: %r" % (disk, ex))

        self.dom.undefine()

    def __dom_info(self):
        keys = ("state", "maxmem", "memory", "cpus", "cputime")
        vals = self.dom.info()
        self.info = dict(zip(keys, vals))

    def __read_desc(self):
        xml = self.dom.XMLDesc(0)
        tree = xmlparse(xml)
        doms = tree.getElementsByTagName("domain")
        if not doms:
            return
        devs = doms[0].getElementsByTagName("devices")
        if not devs:
            return
        ifaces = devs[0].getElementsByTagName("interface")
        if ifaces:
            macs = [iface.getElementsByTagName("mac") for iface in ifaces]
            addrs = [mac[0].getAttribute("address") for mac in macs if mac]
            self.macs = [str(addr) for addr in addrs]
        disks = devs[0].getElementsByTagName("disk")
        if disks:
            sources = [disk.getElementsByTagName("source") for disk in disks]
            files = [source[0].getAttribute("file") for source in sources if source]
            self.disks = [str(f) for f in files]


def mac_to_ipv6(prefix, mac):
    mp = mac.split(":")
    inv_a = int(mp[0], 16) ^ 2
    addr = "%s%02x%02x:%02xff:fe%02x:%02x%02x" % \
        (prefix, inv_a, int(mp[1], 16), int(mp[2], 16),
         int(mp[3], 16), int(mp[4], 16), int(mp[5], 16))
    name = socket.getnameinfo((addr, 22), socket.NI_NUMERICSERV)
    return name[0]
