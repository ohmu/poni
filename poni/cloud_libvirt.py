"""
LibVirt provider for Poni.
Copyright (C) 2011-2012 F-Secure Corporation, Helsinki, Finland.
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

import DNS
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

def _lv_dns_lookup(name, qtype):
    """DNS lookup using PyDNS, handles retry over TCP in case of truncation
    and returns a list of results."""
    req = DNS.Request(name=name, qtype=qtype)
    response = req.req()
    if response and response.header["tc"]:
        # truncated, try with tcp
        req = DNS.Request(name=name, qtype=qtype, protocol="tcp")
        response = req.req()
    if not response or not response.answers:
        return []
    result = []
    for a in response.answers:
        if a["typename"].lower() != qtype.lower():
            continue
        if isinstance(a["data"], list):
            result.extend(a["data"])
        else:
            result.append(a["data"])
    return result

class LVPError(CloudError):
    """LibvirtProvider error"""

class LibvirtProvider(Provider):
    def __init__(self, cloud_prop):
        Provider.__init__(self, 'libvirt', cloud_prop)
        self.log = logging.getLogger("poni.libvirt")
        self.instances = {}
        self.ssh_key = None
        profile = json.load(open(cloud_prop["profile"], "rb"))
        if "ssh_key" in profile:
            self.ssh_key = os.path.expandvars(os.path.expanduser(profile["ssh_key"]))

        # Look up all hypervisor hosts, they can be defined one-by-one
        # ("nodes" property) in which case we use the highest priorities
        # with them.  They can also be defined in SRV records in "services"
        # property as well as an older style "nodesets" property without
        # service information in which case we use _libvirt._tcp.
        if not DNS.defaults["server"]:
            DNS.DiscoverNameServers()
        hosts = {}
        for entry in profile.get("nodes", []):
            host, _, port = entry.partition(":")
            hosts["{0}:{1}".format(host, port or 22)] = (0, 100)
        services = set(profile.get("services", []))
        services.update("_libvirt._tcp.{0}".format(host) for host in profile.get("nodesets", []))
        for entry in services:
            for priority, weight, port, host in _lv_dns_lookup(entry, "SRV"):
                hosts["{0}:{1}".format(host, port)] = (priority, weight)
        self.hosts = hosts
        self.hosts_online = None

    @classmethod
    def get_provider_key(cls, cloud_prop):
        """
        Return a cloud Provider object for the given cloud properties.
        """
        return "PONILV"

    def conns(self):
        if self.hosts_online is None:
            if libvirt.getVersion() < 9004:
                # libvirt support for no_verify was introduced in 0.9.4
                procs = []
                for host in self.hosts.iterkeys():
                    args = ["/usr/bin/ssh", "-oBatchMode=yes", "-oStrictHostKeyChecking=no",
                            "root@{0}".format(host), "uptime"]
                    procs.append(subprocess.Popen(args))
                [proc.wait() for proc in procs]

            self.hosts_online = []
            for host, (priority, weight) in self.hosts.iteritems():
                try:
                    conn = PoniLVConn(host, keyfile=self.ssh_key, priority=priority, weight=weight)
                    conn.connect()
                    self.hosts_online.append(conn)
                except libvirt.libvirtError, ex:
                    self.log.warn("Connection to %r failed: %r", conn.uri, ex)

        if not self.hosts_online:
            raise LVPError("No VM hosts available")
        return list(self.hosts_online)

    def disconnect(self):
        self.hosts_online = None

    def __get_instance(self, prop):
        vm_name = instance_id = prop.get('vm_name', None)
        assert vm_name, "vm_name must be specified for libvirt instances"
        instance = self.instances.get(instance_id)
        if not instance:
            vm_conns = []
            vm_state = 'VM_NON_EXISTENT'
            for conn in self.conns():
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
        home = os.getenv("HOME")
        proplist = list(props)
        cloning_start = time.time()

        self.log.info("deleting existing VM instances")
        for prop in proplist:
            instance = self.__get_instance(prop)
            if instance["vm_state"] == "VM_DIRTY":
                # Delete any existing instances
                for conn in instance["vm_conns"]:
                    self.log.info("deleting %r on %r", instance["vm_name"], conn.host)
                    conn.delete_vm(instance["vm_name"])
                instance["vm_state"] = "VM_NON_EXISTENT"
                instance["vm_conns"] = []

        self.log.info("cloning VM instances")
        conns = [conn for conn in self.conns() if conn.srv_weight > 0]
        for prop in proplist:
            instance = self.__get_instance(prop)
            ipv6pre = prop.get("ipv6_prefix")

            if instance["vm_state"] == "VM_RUNNING":
                continue # done
            if instance["vm_state"] != "VM_NON_EXISTENT":
                continue # XXX: throw an error?

            # Select the best place for this host first filtering out nodes
            # with zero-weight and ones included in the exclude list or
            # missing from the include list.
            cands = list(conns)
            if prop.get("hosts", {}).get("exclude"):
                cands = (conn for conn in cands if prop["hosts"]["exclude"] not in conn.host)
            if prop.get("hosts", {}).get("include"):
                cands = (conn for conn in cands if prop["hosts"]["include"] in conn.host)
            # Only consider the entries with the highest priority (lowest service priority value)
            result = sorted((-conn.srv_priority, conn.weight, conn) for conn in cands)
            if not result:
                raise LVPError("No connection available for cloning {0}".format(instance["vm_name"]))
            conn = result[-1][-1]

            self.log.info("cloning %r on %r", instance["vm_name"], conn.host)
            vm = conn.clone_vm(instance["vm_name"], prop, overwrite = True)
            instance["vm_state"] = "VM_RUNNING"
            instance["vm_conns"] = [conn]
            instance["ipproto"] = prop.get("ipproto", "ipv4")
            instance["ipv6"] = vm.ipv6_addr(ipv6pre)[0]
            instance["ssh_key"] = "{0}/.ssh/{1}".format(home, prop["ssh_key"])
        self.log.info("cloning done: took %.2fs" % (time.time() - cloning_start))

        # get ipv4 addresses for the hosts (XXX: come up with something better)
        result = {}
        tunnels = {}
        failed = []
        objs = []
        timeout = 120
        start = time.time()

        for attempt in xrange(1, 1000):
            elapsed = time.time() - start
            if elapsed > timeout:
                raise LVPError("Connecting to %r failed" % (failed, ))
            if attempt > 1:
                time.sleep(2)
            self.log.info("getting ip addresses: round #%r, time spent=%.02fs", attempt, elapsed)
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
                    client.connect(conn.host, port=conn.port, username=conn.username, key_filename=conn.keyfile)
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
                    exec_start = time.time()
                    while (not cmdchan.exit_status_ready()) and ((time.time() - exec_start) < 10.0):
                        time.sleep(0.05)

                    if cmdchan.exit_status_ready():
                        exit_code = cmdchan.recv_exit_status()
                        if exit_code != 0:
                            self.log.warning("remote command non-zero exit status: exitcode=%s, %r", exit_code, instance)

                    data = cmdchan.recv(1024)
                    objs.extend((tunchan, cmdchan, client))
                except (socket.error, socket.gaierror, paramiko.SSHException), ex:
                    self.log.warning("connecting to %r [%s] failed: %r", instance, instance["ipv6"], ex)
                else:
                    if data:
                        ipv4 = data.partition(" inet ")[2].partition("/")[0]
                    else:
                        self.log.warning("no data received from: %r", instance)

                if not ipv4:
                    failed.append(instance)
                else:
                    self.log.info("Got address %r for %s", ipv4, instance["vm_name"])
                    instance['ipv4'] = ipv4
                    addr = instance[instance['ipproto']]
                    result[instance_id] = dict(host=addr, private=dict(ip=addr, dns=addr))

            if not failed:
                break

        [client.close() for client in tunnels.itervalues()]
        self.disconnect()
        return result


class PoniLVXmlOb(object):
    """Libvirt XML tree reader"""
    def __init__(self, xml=None, tree=None, path=None):
        self.__path = path or []
        self.__tree = tree
        if xml is not None:
            self.__tree = xmlparse(xml)

    def __len__(self):
        return self.__tree and 1 or 0

    def __repr__(self):
        return "PoniLVXmlOb(%s)" % (".".join(self.__path))

    def __str__(self):
        return self.__tree and self.__tree.firstChild.wholeText.strip()

    def __getitem__(self, name):
        attr = self.__tree and self.__tree.getAttribute(name)
        if attr is None:
            raise KeyError("%s attribute not found" % name)
        return attr

    def get(self, name):
        return self.__tree and self.__tree.getAttribute(name)

    def __getattr__(self, name):
        if not self.__tree:
            return PoniLVXmlOb()
        elem = self.__tree.getElementsByTagName(name)
        if elem:
            return PoniLVXmlOb(tree=elem[0], path=self.__path+[name])
        if name.endswith("_list"):
            name = name[:-5]
            elems = self.__tree.getElementsByTagName(name)
            return [PoniLVXmlOb(tree=elem, path=self.__path+[name]) for elem in elems]
        return PoniLVXmlOb()

class PoniLVConn(object):
    def __init__(self, host, port=None, uri=None, keyfile=None, priority=None, weight=None):
        if ":" in host:
            host, _, port = host.rpartition(":")
        port = int(port or 22)
        if not uri:
            uri = "qemu+ssh://root@{0}:{1}/system?no_tty=1&no_verify=1&keyfile={2}".\
                  format(host, port, keyfile or "")
        m = re.search("://(.+?)@", uri)
        self.username = m and m.group(1)
        self.keyfile = keyfile
        self.host = host
        self.port = port
        self.uri = uri
        self.srv_priority = 1 if priority is None else priority
        self.srv_weight = 1 if weight is None else weight
        self.conn = None
        self.vms = None
        self.vms_online = 0
        self.vms_offline = 0
        self.cpus_online = 0
        self.ram_online = 0
        self.pools = None
        self.node = None
        self.info = None

    def __repr__(self):
        return "PoniLVConn(%r)" % (self.host)

    @property
    def weight(self):
        """calculate a weight for this node based on its cpus and ram"""
        counters = {
            "total_mhz": self.vms_online + self.cpus_online/4.0,
            "memory": self.vms_online + self.ram_online/4096.0,
        }
        load_w = sum((self.node[k] / float(v or 1)) / self.node[k] for k, v in counters.iteritems())
        return load_w * self.srv_weight

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
        self.info = node

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
        doms = [dom for dom in self.vms.itervalues() if dom.info["cputime"] > 0]
        self.cpus_online = sum(dom.info["cpus"] for dom in doms)
        self.ram_online = sum(dom.info["maxmem"]/1024 for dom in doms)

    def delete_vm(self, vm_name):
        if vm_name not in self.vms:
            raise LVPError("%r is not defined" % (vm_name, ))
        self.vms[vm_name].delete()
        self.refresh_list()

    def clone_vm(self, name, spec, overwrite = False):
        desc = """
            <domain type='kvm'>
              <name>%(name)s</name>
              <description>%(desc)s</description>
              <uuid>%(uuid)s</uuid>
              <memory>%(hardware.ram_kb)s</memory>
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
                %(disks)s
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
        disk_desc = """
                <disk type='%(disk_type)s' device='disk'>
                  <driver name='qemu' type='%(driver_type)s' cache='%(cache)s'/>
                  <source %(source)s='%(path)s'/>
                  <target dev='%(target_dev)s'/>
                </disk>
                """
        spec = copy.deepcopy(spec)
        def macaddr(index):
            """create a mac address based on the VM name for DHCP predictability"""
            mac_ext = hashlib.md5(name).hexdigest()
            return "52:54:00:%s:%s:%02x" % (mac_ext[0:2], mac_ext[2:4], int(mac_ext[4:6], 16)^index)
        def gethw(prefix):
            """grab all relevant hardware entries from spec"""
            fp = "hardware."+prefix
            rel = sorted((int(k[len(fp):]), k) for k in spec.iterkeys() if k.startswith(fp))
            return [spec[k] for i, k in rel]

        if name in self.vms:
            if not overwrite:
                raise LVPError("%r vm already exists" % (name, ))
            self.delete_vm(name)
        spec["name"] = name
        if "desc" not in spec:
            spec["desc"] = "created by poni.cloud_libvirt by {0}@{1} on {2}+00:00".format(
                os.getenv("USER"), socket.gethostname(), datetime.datetime.utcnow().isoformat()[0:19])
        if "uuid" not in spec:
            spec["uuid"] = str(uuid.uuid4())
        if isinstance(spec.get("hardware"), dict):
            for k, v in spec["hardware"].iteritems():
                spec["hardware.%s" % (k, )] = v

        # default to x86_64 system with 1 CPU and 1G RAM
        if "hardware.arch" not in spec:
            spec["hardware.arch"] = "x86_64"
        if "hardware.cpus" not in spec:
            spec["hardware.cpus"] = 1
        ram_mb = spec.get("hardware.ram_mb", spec.get("hardware.ram", 1024))
        ram_kb = spec.get("hardware.ram_kb", 1024 * ram_mb)
        spec["hardware.ram_kb"] = ram_kb
        spec["hardware.ram_mb"] = ram_kb // 1024

        # Set up disks - find all hardware.diskX entries in spec
        spec["disks"] = ""
        for i, item in enumerate(gethw("disk")):
            dev_name = "vd" + chr(ord("a") + i)
            if "clone" in item or "create" in item:
                pool = self.pools[item["pool"]]
                vol_name = "%s-%s" % (name, dev_name)
                if "clone" in item:
                    vol = pool.clone_volume(item["clone"], vol_name, item.get("size"), overwrite = overwrite)
                if "create" in item:
                    vol = pool.create_volume(vol_name, item["size"], overwrite = overwrite)
                disk_path = vol.path
                disk_type = vol.device
                driver_type = vol.format
            elif "file" in item:
                disk_path = item["file"]
                disk_type = "file"
                driver_type = item.get("driver", "qcow2")
            elif "dev" in item:
                disk_path = item["dev"]
                disk_type = "block"
                driver_type = "raw"
            else:
                raise LVPError("Unrecognized disk specification %r" % (item, ))

            dspec = {
                "path": disk_path,
                "disk_type": disk_type,
                "driver_type": driver_type,
                "cache": item.get("cache", "writeback"),
                "source": "dev" if disk_type == "block" else "file",
                "target_dev": dev_name,
            }
            spec["disks"] += disk_desc % dspec

        # Set up interfaces - any hardware.nicX entries in spec,
        default_network = spec.get("default_network", "default")
        spec["interfaces"] = ""
        items = gethw("nic") or [{}]
        for i, item in enumerate(items):
            ispec = {
                "mac": item.get("mac", macaddr(i)),
                "type": item.get("type", "network"),
                "network": item.get("network", default_network),
            }
            if "bridge" in item: # support for old style bridge-only defs
                ispec["type"] = "bridge"
                ispec["network"] = item["bridge"]
            spec["interfaces"] += interface_desc % ispec

        new_desc = desc % spec
        vm = self.conn.defineXML(new_desc)
        vm.create()
        self.refresh_list()
        return self.vms[name]

class PoniLVVol(object):
    def __init__(self, vol, pool):
        self.vol = vol
        self.pool = pool
        self.path = vol.path()
        self.format = None
        self.device = None
        self.__read_desc()

    def __read_desc(self):
        xml = PoniLVXmlOb(self.vol.XMLDesc(0))
        tformat = xml.volume.target.format.get("type")
        self.format = tformat or "raw"
        self.device = "block" if xml.volume.source.device else "file"

class PoniLVPool(object):
    def __init__(self, pool):
        self.pool = pool
        self.path = None
        self.type = None
        self.info = None
        self.__read_desc()
        self.__pool_info()

    def __pool_info(self):
        vals = self.pool.info()
        self.info = {
            "capacity": vals[1]/(1024*1024),
            "used": vals[2]/(1024*1024),
            "free": vals[3]/(1024*1024),
        }

    def _define_volume(self, target, megabytes, source, overwrite):
        spec = {
            "name": "auto.%s" % target,
            "backing": "",
            "size": (megabytes or 0) * 1024 * 1024,
            "format": "qcow2",
            "ext": ".qcow2",
        }
        if self.type == "logical":
            spec["ext"] = ""
            spec["format"] = "raw"
        if source:
            orig = self.pool.storageVolLookupByName(source)
            spec["backing"] = """
                <backingStore>
                    <format type='qcow2'/>
                    <path>%s</path>
                </backingStore>
                """ % orig.path()
            if not megabytes:
                spec["size"] = orig.info()[1]
        spec["fullname"] = "%(name)s%(ext)s" % spec
        desc = """
            <volume>
                <name>%(fullname)s</name>
                <capacity>%(size)s</capacity>
                <target>
                    <format type='%(format)s'/>
                </target>
                %(backing)s
            </volume>
            """ % spec

        try:
            vol = self.pool.createXML(desc, 0)
        except libvirt.libvirtError, ex:
            if "storage vol already exists" not in str(ex):
                raise
            if not overwrite:
                raise LVPError("%r volume already exists" % (spec["fullname"], ))
            self.delete_volume(spec["fullname"])
            vol = self.pool.createXML(desc, 0)

        return PoniLVVol(vol, self)

    def create_volume(self, target, megabytes, overwrite=False):
        return self._define_volume(target, megabytes, None, overwrite)

    def clone_volume(self, source, target, megabytes=None, overwrite=False):
        return self._define_volume(target, megabytes, source, overwrite)

    def delete_volume(self, name):
        self.pool.storageVolLookupByName(name).delete(0)

    def __read_desc(self):
        xml = PoniLVXmlOb(self.pool.XMLDesc(0))
        self.type = xml.pool["type"]
        self.path = str(xml.pool.target.path)


class PoniLVDom(object):
    def __init__(self, conn, dom):
        self.log = logging.getLogger("poni.libvirt.dom")
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

        # delete snapshots
        for name in self.dom.snapshotListNames(0):
            self.log.info("Deleting snapshot: %s" % (name,))
            snapshot = self.dom.snapshotLookupByName(name, 0)
            snapshot.delete(0)

        self.dom.undefine()

    def __dom_info(self):
        keys = ("state", "maxmem", "memory", "cpus", "cputime")
        vals = self.dom.info()
        self.info = dict(zip(keys, vals))

    def __read_desc(self):
        xml = PoniLVXmlOb(self.dom.XMLDesc(0))
        devs = xml.domain.devices
        if devs:
            self.macs = [str(iface.mac["address"]) for iface in devs.interface_list]
            self.disks = [str(disk.source.get("file") or disk.source.get("dev")) for disk in devs.disk_list]


def mac_to_ipv6(prefix, mac):
    mp = mac.split(":")
    inv_a = int(mp[0], 16) ^ 2
    addr = "%s%02x%02x:%02xff:fe%02x:%02x%02x" % \
        (prefix, inv_a, int(mp[1], 16), int(mp[2], 16),
         int(mp[3], 16), int(mp[4], 16), int(mp[5], 16))
    name = socket.getnameinfo((addr, 22), socket.NI_NUMERICSERV)
    return name[0]
