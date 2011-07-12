"""
LibVirt provider for Poni.
Copyright (C) 2011 F-Secure Corporation, Helsinki, Finland.
Author: Oskari Saarenmaa <ext-oskari.saarenmaa@f-secure.com>
"""

import copy
import datetime
import getpass
import hashlib
import logging
import os
import paramiko
import random
import socket
import subprocess
import time
import uuid
from xml.dom.minidom import parseString as xmlparse

import libvirt
from poni.cloudbase import Provider
from poni.errors import CloudError

class LVPError(CloudError):
    """LibvirtProvider error"""

class LibvirtProvider(Provider):
    def __init__(self, cloud_prop):
        Provider.__init__(self, self.get_provider_key(cloud_prop), cloud_prop)
        self.log = logging.getLogger("poni.libvirt")
        self.hosts = []
        self.hosts_online = None
        self.instances = {}
        hosts = os.environ.get('LV_HOSTS') or cloud_prop.get("lv_hosts")
        assert hosts, "either the enviroment variable LV_HOSTS or lv_hosts property must be set for libvirt instances"
        for hosts1 in hosts.split(","):
            for host in hosts1.split():
                url = "qemu+ssh://root@%s/system" % (host, )
                self.hosts.append(PoniLVConn(host, url))

    @classmethod
    def get_provider_key(cls, cloud_prop):
        """
        Return a cloud Provider object for the given cloud properties.
        """
        return "PONILV"

    @property
    def conns(self):
        if not self.hosts_online:
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
        fwds = {}
        home = os.environ.get("HOME")
        for prop in props:
            instance_id = prop['instance']
            instance = self.__get_instance(prop)
            vm_state = instance['vm_state']
            pool = prop.get("storage_pool", "default")
            ipv6pre = prop.get("ipv6_prefix")

            if vm_state == "VM_DIRTY":
                conns = instance["vm_conns"]
                if len(conns) > 1:
                    [conn.delete_vm(instance["vm_name"]) for conn in conns]
                conn = random.choice(conns)
            elif vm_state == "VM_NON_EXISTENT":
                conn = random.choice(self.conns)
            elif vm_state == "VM_RUNNING":
                continue
            else:
                continue # XXX: throw an error?
            vm = conn.clone_vm(instance["vm_name"], pool, prop, overwrite = True)
            ipv6_addr = vm.ipv6_addr(ipv6pre)
            tun_port = random.randint(30000, 60000)
            if conn.host not in fwds:
                fwds[conn.host] = []
            fwds[conn.host].append("-L%d:[%s]:22" % (tun_port, ipv6_addr[0]))
            self.instances[instance_id]['ipproto'] = prop.get("ipproto", "ipv4")
            self.instances[instance_id]['ipv6'] = ipv6_addr[0]
            self.instances[instance_id]['tunnel_port'] = tun_port
            self.instances[instance_id]["vm_state"] = "VM_RUNNING"
            ssh_key_path = "%s/.ssh/%s" % (home, prop["ssh_key"])
            self.instances[instance_id]["ssh_key"] = ssh_key_path

        # get ipv4 addresses for the hosts (XXX: come up with something better)
        result = {}

        # fire up ssh tunnels
        tuns = []
        for host, ports in fwds.iteritems():
            args = ["/usr/bin/ssh"] + ports + ["root@%s" % (host, ), "sleep 120"]
            print args
            tuns.append(subprocess.Popen(args, stdout=subprocess.PIPE, stdin=subprocess.PIPE))

        # look up addresses
        missing = 1
        while missing:
            missing = 0
            for instance_id, instance in self.instances.iteritems():
                if "tunnel_port" not in instance:
                    continue
                if "ipv4" in instance:
                    continue
                try:
                    client = paramiko.SSHClient()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    client.connect("localhost", port = int(instance["tunnel_port"]), username = "root",
                        key_filename = instance["ssh_key"])
                    stdin, stdout, stderr = client.exec_command('ip -4 addr show scope global')
                    data = stdout.read()
                    client.close()
                except (socket.error, paramiko.SSHException), ex:
                    self.log.warning("connecting to %r failed: %r", instance, ex)
                    if "failures" not in instance:
                        instance["failures"] = 1
                    else:
                        instance["failures"] += 1
                    if instance["failures"] > 10:
                        raise LVPError("%r failed" % (instance, ))
                    missing += 1
                    continue

                if not data:
                    missing += 1
                    continue
                ipv4 = data.partition(" inet ")[2].partition("/")[0]
                if not ipv4:
                    missing += 1
                    continue
                instance['ipv4'] = ipv4

                addr = instance[instance['ipproto']]
                result[instance_id] = dict(host=addr, private=dict(ip=addr, dns=addr))
            time.sleep(2)

        [tun.kill() for tun in tuns]
        return result


class PoniLVConn(object):
    def __init__(self, host, uri):
        self.host = host
        self.uri = uri
        self.conn = None
        self.vms = None
        self.pools = None

    def __repr__(self):
        return "PoniLVConn(%r)" % (self.host)

    def connect(self, uri = None):
        self.conn = libvirt.open(uri or self.uri)
        self.list()

    def list(self):
        self.vms = {}
        for dom_id in self.conn.listDomainsID():
            dom = PoniLVDom(self, self.conn.lookupByID(dom_id))
            self.vms[dom.name] = dom
        for name in self.conn.listDefinedDomains():
            dom = PoniLVDom(self, self.conn.lookupByName(name))
            self.vms[dom.name] = dom
        self.pools = {}
        for name in self.conn.listStoragePools():
            pool = PoniLVPool(self.conn.storagePoolLookupByName(name))
            self.pools[name] = pool

    def delete_vm(self, vm_name):
        if vm_name not in self.vms:
            raise LVPError("%r is not defined" % (vm_name, ))
        self.vms[vm_name].delete()
        self.list() # refresh

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
        self.list() # refresh
        return self.vms[name]


class PoniLVPool(object):
    def __init__(self, pool):
        self.pool = pool
        self.xml = pool.XMLDesc(0)
        self.path = None
        self.parse_xml()

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

    def parse_xml(self):
        tree = xmlparse(self.xml)
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
        self.xml = dom.XMLDesc(0)
        self.macs = []
        self.disks = []
        self.parse_xml()

    def ipv6_addr(self, prefix = "fe80::"):
        return [mac_to_ipv6(prefix, mac) for mac in self.macs]

    def delete(self):
        # lookup and delete storage
        for disk in self.disks:
            delete_ok = False
            delete_ex = []
            try:
                vol = self.conn.conn.storageVolLookupByPath(disk)
                vol.delete(0)
            except libvirt.libvirtError, ex:
                raise LVPError("%r: deletion failed: %r" % (disk, ex))
        try:
            self.dom.destroy()
        except libvirt.libvirtError, ex:
            if "domain is not running" not in str(ex):
                raise
        self.dom.undefine()

    def parse_xml(self):
        tree = xmlparse(self.xml)
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
