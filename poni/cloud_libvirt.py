"""
LibVirt provider for Poni.
Copyright (C) 2011-2013 F-Secure Corporation, Helsinki, Finland.
Author: Oskari Saarenmaa <ext-oskari.saarenmaa@f-secure.com>
"""

from poni import util
from poni.cloudbase import Provider
from poni.errors import CloudError
import copy
import datetime
import getpass
import hashlib
import json
import logging
import os
import paramiko
import random
import re
import socket
import subprocess
import threading
import time
import uuid

MISSING_LIBS = []
try:
    import DNS
except ImportError:
    DNS = None
    MISSING_LIBS.append("DNS")

try:
    import libvirt
except ImportError:
    libvirt = None
    MISSING_LIBS.append("libvirt")

try:
    from lxml import etree
    from lxml.builder import E as XMLE
except ImportError:
    etree = None
    XMLE = None
    MISSING_LIBS.append("lxml")


if getattr(paramiko.SSHClient, "connect_socket", None):
    SshClientLVP = paramiko.SSHClient
else:
    class SSHClientLVP(paramiko.SSHClient):
        def connect_socket(self, sock, username, key_filename):
            self._transport = paramiko.Transport(sock)
            if self._log_channel is not None:
                self._transport.set_log_channel(self._log_channel)
            self._transport.start_client()
            paramiko.resource.ResourceManager.register(self, self._transport)  # pylint: disable=E1120
            self._auth(username or getpass.getuser(), None, None, [key_filename], False, False)


def _do_dns_lookup(req, max_retries=3):
    "Make a DNS lookup and retry on DNS timeouts"
    tri = 0
    while tri < max_retries:
        try:
            return req.req()
        except DNS.Base.DNSError:
            # probably should be some logging here
            time.sleep(1)
            tri += 1
    raise


def _lv_dns_lookup(name, qtype):
    """DNS lookup using PyDNS, handles retry over TCP in case of truncation
    and returns a list of results."""
    req = DNS.Request(name=name, qtype=qtype)
    response = _do_dns_lookup(req)
    if response and response.header["tc"]:
        # truncated, try with tcp
        req = DNS.Request(name=name, qtype=qtype, protocol="tcp")
        response = _do_dns_lookup(req)
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


def _created_str():
    return "created by poni.cloud_libvirt by {0}@{1} on {2}+00:00".format(
        os.getenv("USER"), socket.gethostname(), datetime.datetime.utcnow().isoformat()[0:19])


class LVPError(CloudError):
    """LibvirtProvider error"""
    def __init__(self, msg, code=None):
        CloudError.__init__(self, msg)
        self.code = code

    def get_error_code(self):
        return self.code


def convert_libvirt_errors(method):
    """Convert libvirt errors to LVPError"""
    def wrapper(self, *args, **kw):
        try:
            return method(self, *args, **kw)
        except libvirt.libvirtError as ex:
            code = ex.get_error_code()
            exstr = str(ex).lower()
            if code == libvirt.VIR_ERR_NO_DOMAIN_SNAPSHOT:
                err = "snapshot_not_found"
                msg = "snapshot {0!r} not found for {1!r}".format(args[0], self.name)
            elif "domain is already running" in exstr:
                # code == libvirt.VIR_ERR_OPERATION_INVALID
                err = "vm_online"
                msg = "vm {0!r} is already running".format(self.name)
            elif "domain is not running" in exstr:
                # code == libvirt.VIR_ERR_OPERATION_INVALID
                err = "vm_offline"
                msg = "vm {0!r} is not running".format(self.name)
            elif re.search("snapshot file for disk \S+ already exists", exstr) or \
                 re.search("domain snapshot \S+ already exists", exstr):
                # code == libvirt.VIR_ERR_CONFIG_UNSUPPORTED or libvirt.VIR_ERR_INTERNAL_ERROR
                err = "snapshot_exists"
                msg = "snapshot {0!r} already exists for {1!r}".format(args[0], self.name)
            else:
                raise LVPError("unexpected libvirt error: {0.__class__.__name__}: {0}".format(ex), code=code)

            if err not in getattr(method, "ignore_libvirt_errors", []):
                raise LVPError(msg, code=code)

    wrapper.__doc__ = method.__doc__
    wrapper.__name__ = method.__name__
    return wrapper


def ignore_libvirt_errors(*errs):
    """Mark various errors to be ignored"""
    def decorate(method):
        method.ignore_libvirt_errors = errs
        return method
    return decorate


class LibvirtProvider(Provider):
    def __init__(self, cloud_prop):
        if MISSING_LIBS:
            raise CloudError("missing libraries required by libvirt deployment: " + ", ".join(MISSING_LIBS))

        Provider.__init__(self, "libvirt", cloud_prop)
        self.log = logging.getLogger("poni.libvirt")
        self.ssh_key = None
        profile_file = cloud_prop.get("profile")
        if not profile_file:
            raise CloudError("required node property 'cloud.profile' pointing to a profile file not defined")

        profile = json.load(open(profile_file, "rb"))
        self.hypervisor = profile.get("hypervisor", "kvm")
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
                for hostport in self.hosts.iterkeys():
                    host, _, port = hostport.partition(':')
                    args = ["/usr/bin/ssh", "-oBatchMode=yes", "-oStrictHostKeyChecking=no",
                            "-p{0}".format(port), "root@{0}".format(host), "uptime"]
                    procs.append(subprocess.Popen(args))
                [proc.wait() for proc in procs]

            self.hosts_online = []

            def lv_connect(host, priority, weight):
                try:
                    conn = PoniLVConn(host, hypervisor=self.hypervisor, keyfile=self.ssh_key,
                                      priority=priority, weight=weight)
                    conn.connect()
                    self.hosts_online.append(conn)
                except (LVPError, libvirt.libvirtError) as ex:
                    self.log.warn("Connection to %r failed: %r", conn.uri, ex)

            tasks = util.TaskPool()
            for host, (priority, weight) in self.hosts.iteritems():
                tasks.apply_async(lv_connect, [host, priority, weight])

            tasks.wait_all()

        if not self.hosts_online:
            raise LVPError("No VM hosts available")
        return list(self.hosts_online)

    def disconnect(self):
        self.hosts_online = None

    def __get_instances(self, props, non_existent=False):
        vms = {}
        tasks = util.TaskPool()

        def add_vms(conn):
            conn.refresh()
            for vm_name in conn.dominfo.vms:
                vms.setdefault(vm_name, []).append(conn)

        for conn in self.conns():
            tasks.apply_async(add_vms, [conn])

        tasks.wait_all()

        props = dict((prop["vm_name"], prop) for prop in props)
        for vm_name, prop in props.iteritems():
            if vm_name in vms:
                yield dict(vm_name=vm_name, vm_state="VM_DIRTY", vm_conns=vms[vm_name], prop=prop)
            elif non_existent:
                yield dict(vm_name=vm_name, vm_state="VM_NON_EXISTENT", vm_conns=[], prop=prop)

    def __get_vms(self, props):
        for instance in self.__get_instances(props):
            for conn in instance['vm_conns']:
                self.log.debug("found %r from %r", instance['vm_name'], conn)
                yield conn.dominfo.vms[instance['vm_name']]

    def init_instance(self, prop):
        """
        Create a new instance with the given properties.

        Returns node properties that are changed.
        """
        out_prop = copy.deepcopy(prop)
        out_prop["instance"] = prop["vm_name"]
        return dict(cloud=out_prop)

    def delete_vm(self, conn, instance):
        """Delete a VM instance"""
        self.log.info("deleting %r on %r", instance["vm_name"], conn.host)
        conn.delete_vm(instance["vm_name"])

    def terminate_instances(self, props):
        """
        Terminate instances specified in the given sequence of cloud
        properties dicts.
        """
        tasks = util.TaskPool()
        for instance in self.__get_instances(props):
            for conn in instance["vm_conns"]:
                tasks.apply_async(self.delete_vm, [conn, instance])

        tasks.wait_all()

    def weighted_random_choice(self, cands):
        """Weighted random selection of a single target host from a list of candidates"""
        # Only consider the entries with the highest priority (lowest service priority value)
        lowest_priority = min(conn.srv_priority for conn in cands)
        result = sorted(((conn.weight, conn) for conn in cands
                         if conn.srv_priority == lowest_priority),
                        reverse=True)
        if not result:
            raise LVPError("No connection available for cloning")

        total_weight = sum(e[0] for e in result)
        random_pos = random.random() * total_weight
        weight_pos = 0.0
        for weight, conn in result:
            weight_pos += weight
            if weight_pos >= random_pos:
                return conn

        assert False, "execution should never end up here"

    def wait_instances(self, props, wait_state="running"):
        """
        Wait for all the given instances to reach status specified by
        the 'wait_state' argument.

        Returns a dict {instance_id: dict(<updated properties>)}
        """
        assert wait_state == "running", "libvirt only handles running stuff"
        home = os.getenv("HOME")
        # collapse props to one entry per vm_name
        props = dict((prop["vm_name"], prop) for prop in props).values()

        instances = self.__get_instances(props)
        self.log.info("deleting existing VM instances")
        delete_started = time.time()
        tasks = util.TaskPool()
        for instance in instances:
            # Delete any existing instances if required to reinit (the
            # default) or if the same VM was found from multiple hosts.
            if instance["prop"].get("reinit", True) or len(instance["vm_conns"]) > 1:
                for conn in instance["vm_conns"]:
                    tasks.apply_async(self.delete_vm, [conn, instance])

        tasks.wait_all()
        cloning_started = time.time()

        def clone_instance(instance):
            prop = instance["prop"]
            ipv6pre = prop.get("ipv6_prefix")

            if instance["vm_state"] == "VM_RUNNING":
                return  # done
            elif instance["vm_state"] == "VM_DIRTY":
                # turn this into an active instance
                vm = instance["vm_conns"][0].dominfo.vms[instance["vm_name"]]
            elif instance["vm_state"] == "VM_NON_EXISTENT":
                # Select the best place for this host first filtering out nodes
                # with zero-weight and ones included in the exclude list or
                # missing from the include list.
                cands = list(conns)
                if prop.get("hosts", {}).get("exclude"):
                    cands = [conn for conn in cands if prop["hosts"]["exclude"] not in conn.host]
                if prop.get("hosts", {}).get("include"):
                    cands = [conn for conn in cands if prop["hosts"]["include"] in conn.host]

                conn = self.weighted_random_choice(cands)
                self.log.info("cloning %r on %r", instance["vm_name"], conn.host)
                vm = conn.clone_vm(instance["vm_name"], prop, overwrite=True)
                instance["vm_conns"] = [conn]
            else:
                return  # XXX

            instance["vm_state"] = "VM_RUNNING"
            instance["ipproto"] = prop.get("ipproto", "ipv4")
            instance["ipv6"] = vm.ipv6_addr(ipv6pre)[0]
            instance["ssh_key"] = "{0}/.ssh/{1}".format(home, prop["ssh_key"])
            instances.append(instance)

        self.log.info("cloning VM instances")
        instances = []
        conns = [conn for conn in self.conns() if conn.srv_weight > 0]
        tasks = util.TaskPool()
        for instance in self.__get_instances(props, non_existent=True):
            tasks.apply_async(clone_instance, [instance])

        tasks.wait_all()
        boot_started = time.time()

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
                raise LVPError("Connecting to {0!r} failed".format(failed))
            if attempt > 1:
                time.sleep(2)
            self.log.info("getting ip addresses: round #%r, time spent=%.02fs", attempt, elapsed)
            failed = []

            for instance in instances:
                instance_id = instance["vm_name"]
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
                    client.connect_socket(tunchan, username="root", key_filename=instance["ssh_key"])
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
                except (socket.error, socket.gaierror, paramiko.SSHException) as ex:
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
                    result[instance_id] = dict(
                        host=addr,
                        private=dict(ip=addr, dns=addr),
                        hypervisor=self.hypervisor)

            if not failed:
                break

        self.log.info("instances ready: delete {1:.2f}s, cloning {2:.2f}s, boot {0:.2f}s".format(
                cloning_started - delete_started, boot_started - cloning_started,
                time.time() - boot_started))

        [client.close() for client in tunnels.itervalues()]
        self.disconnect()
        return result

    def power_on_instances(self, props):
        result = {}
        for vm in self.__get_vms(props):
            vm.power_on()
            result[vm.name] = {'power': 'on'}
        return result

    def power_off_instances(self, props):
        result = {}
        for vm in self.__get_vms(props):
            vm.power_off()
            result[vm.name] = {'power': 'off'}
        return result

    def create_snapshot(self, props, name, description=None, memory=False):
        result = {}
        for vm in self.__get_vms(props):
            vm.create_snapshot(name, description, memory)
            result[vm.name] = {}
        return result

    def remove_snapshot(self, props, name):
        result = {}
        for vm in self.__get_vms(props):
            vm.remove_snapshot(name)
            result[vm.name] = {}
        return result

    def revert_to_snapshot(self, props, name=None):
        result = {}
        for vm in self.__get_vms(props):
            vm.revert_to_snapshot(name)
            result[vm.name] = {}
        return result


class DomainInfo(dict):
    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        elif name in self:
            return self[name]
        else:
            raise AttributeError(name)


class PoniLVConn(object):
    def __init__(self, host, port=None, hypervisor=None, uri=None, keyfile=None, priority=None, weight=None):
        if ":" in host:
            host, _, port = host.rpartition(":")
        port = int(port or 22)
        if not hypervisor or hypervisor == "qemu":
            hypervisor = "kvm"
        if not uri:
            uri = "{hypervisor}+ssh://root@{host}:{port}/{path}" \
                  "?no_tty=1&no_verify=1&keyfile={keyfile}" \
                  .format(host=host, port=port, keyfile=keyfile or "",
                          hypervisor="qemu" if hypervisor == "kvm" else hypervisor,
                          path="system" if hypervisor == "kvm" else "")
        m = re.search("://(.+?)@", uri)
        self.log = logging.getLogger("ponilvconn")
        self.username = m and m.group(1)
        self.keyfile = keyfile
        self.host = host
        self.port = port
        self.hypervisor = hypervisor
        self.emulator = None  # the executable launched by lxc guests
        self.uri = uri
        self.srv_priority = 1 if priority is None else priority
        self.srv_weight = 1 if weight is None else weight
        self.conn = None
        self.node = None
        self.info = None
        self.dominfo = None
        self._dominfo_lock = threading.Lock()

    def __repr__(self):
        return "PoniLVConn({0!r})".format(self.host)

    @property
    def weight(self):
        """calculate a weight for this node based on its cpus and ram"""
        counters = {
            "total_mhz": self.dominfo.vms_online + self.dominfo.cpus_online / 4.0,
            "memory": self.dominfo.vms_online + self.dominfo.ram_online / 4096.0,
        }
        load_w = sum((self.node[k] / float(v or 1)) / self.node[k] for k, v in counters.iteritems())
        return load_w * self.srv_weight

    def connect(self):
        self.conn = libvirt.open(self.uri)
        self.refresh()
        if self.hypervisor == "lxc":
            caps = etree.fromstring(self.conn.getCapabilities())
            self.emulator = caps.find("guest").find("arch").find("emulator").text

    def refresh(self):
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
        """Refresh the domain lists unless someone else is already doing the refresh"""
        if self._dominfo_lock.acquire(False):
            try:
                return self._refresh_list()
            finally:
                self._dominfo_lock.release()
        else:
            # wait until the refresh done by the other party is complete
            with self._dominfo_lock:
                pass

    def _refresh_list(self):
        assert self.conn, "not connected"
        dominfo = DomainInfo(conn=self.conn, pools={}, vms={}, vms_online=0, vms_offline=0)

        for dom_id in self.conn.listDomainsID():
            try:
                dom = PoniLVDom(self, self.conn.lookupByID(dom_id))
            except (LVPError, libvirt.libvirtError) as ex:
                if ex.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
                    continue
                raise
            dominfo.vms[dom.name] = dom
            dominfo["vms_online"] += 1

        for name in self.conn.listDefinedDomains():
            try:
                dom = PoniLVDom(self, self.conn.lookupByName(name))
            except (LVPError, libvirt.libvirtError) as ex:
                if ex.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
                    continue
                raise
            dominfo.vms[dom.name] = dom
            dominfo["vms_offline"] += 1

        for name in self.conn.listStoragePools():
            pool = PoniLVPool(self.conn.storagePoolLookupByName(name))
            dominfo.pools[name] = pool

        doms = [dom for dom in dominfo.vms.itervalues() if dom.info["cputime"] > 0]
        dominfo["cpus_online"] = sum(dom.info["cpus"] for dom in doms)
        dominfo["ram_online"] = sum(dom.info["maxmem"] / 1024 for dom in doms)
        self.dominfo = dominfo  # atomic update of all dom info stats

    @convert_libvirt_errors
    def delete_vm(self, vm_name):
        if vm_name not in self.dominfo.vms:
            raise LVPError("{0!r} is not defined".format(vm_name))
        self.dominfo.vms[vm_name].delete()
        self.refresh_list()

    @convert_libvirt_errors
    def clone_vm(self, name, spec, overwrite=False):
        def macaddr(index):
            """create a mac address based on the VM name for DHCP predictability"""
            mac_ext = hashlib.md5(name).hexdigest()
            return "52:54:00:{0}:{1}:{2:02x}".format(mac_ext[0:2], mac_ext[2:4], int(mac_ext[4:6], 16) ^ index)

        def gethw(prefix):
            """grab all relevant hardware entries from spec"""
            fp = "hardware." + prefix
            rel = sorted((int(k[len(fp):]), k) for k in spec.iterkeys() if k.startswith(fp))
            return [spec[k] for i, k in rel]

        if name in self.dominfo.vms:
            if not overwrite:
                raise LVPError("{0!r} vm already exists".format(name))
            self.delete_vm(name)

        spec = copy.deepcopy(spec)
        if isinstance(spec.get("hardware"), dict):
            for k, v in spec["hardware"].iteritems():
                spec["hardware." + k] = v

        hypervisor = spec.get("hypervisor", self.hypervisor)
        ram_mb = spec.get("hardware.ram_mb", spec.get("hardware.ram", 1024))
        ram_kb = spec.get("hardware.ram_kb", 1024 * ram_mb)

        if hypervisor == "kvm":
            devs = XMLE.devices(
                XMLE.serial(XMLE.target(port="0"), XMLE.alias(name="serial0"), type="pty"),
                XMLE.console(XMLE.target(port="0"), XMLE.alias(name="serial0"), type="pty"),
                XMLE.input(XMLE.alias(name="input0"), type="tablet", bus="usb"),
                XMLE.input(type="mouse", bus="ps2"),
                XMLE.graphics(type="vnc", autoport="yes"),
                XMLE.video(
                    XMLE.model(type="cirrus", vram="9216", heads="1"),
                    XMLE.alias(name="video0")),
                XMLE.memballoon(XMLE.alias(name="balloon0"), model="virtio"))
            extra = [
                XMLE.cpu(mode=spec.get("hardware.cpumode", "host-model")),
                XMLE.features(XMLE.acpi(), XMLE.apic(), XMLE.pae()),
                XMLE.os(
                    XMLE.type("hvm", machine="pc", arch=spec.get("hardware.arch", "x86_64")),
                    XMLE.boot(dev="hd")),
                ]
        elif hypervisor == "lxc":
            devs = XMLE.devices(
                XMLE.emulator(self.emulator),
                XMLE.console(
                    XMLE.target(type="lxc", port="0"),
                    XMLE.alias(name="console0"),
                    type="pty"))
            extra = [
                XMLE.resource(XMLE.partition("/machine")),
                XMLE.os(
                    XMLE.type("exe", arch=spec.get("hardware.arch", "x86_64")),
                    XMLE.init(spec.get("init", "/sbin/init"))),
                XMLE.seclabel(type="none"),
                ]
        else:
            raise LVPError("unknown hypervisor type {0!r}".format(hypervisor))

        desc = XMLE.domain(
            XMLE.name(name),
            XMLE.description(spec.get("desc", _created_str())),
            XMLE.uuid(spec.get("uuid", str(uuid.uuid4()))),
            XMLE.clock(offset="utc"),
            XMLE.on_poweroff("destroy"),
            XMLE.on_reboot("restart"),
            XMLE.on_crash("restart"),
            XMLE.memory(str(ram_kb)),
            XMLE.vcpu(str(spec.get("hardware.cpus", 1))),
            devs, *extra,
            type=hypervisor)

        # Set up disks - find all hardware.diskX entries in spec
        for i, item in enumerate(gethw("disk")):
            # we want to name the devices/files created on the host sides with names the kvm guests
            # will see (ie vda, vdb, etc) but lxc hosts don't really see devices, instead we just
            # have target directories
            if hypervisor == "lxc":
                dev_name = str(i)
                target_dir = item.get("target")
            else:
                dev_name = "vd" + chr(ord("a") + i)
                target_dir = None
            if "clone" in item or "create" in item:
                try:
                    pool = self.dominfo.pools[item["pool"]]
                except KeyError:
                    raise LVPError("host {0}:{1} does not have pool named '{2}'".format(
                            self.host, self.port, item["pool"]))

                vol_name = "{0}-{1}".format(name, dev_name)
                if "clone" in item:
                    vol = pool.clone_volume(item["clone"], vol_name, item.get("size"), overwrite=overwrite, voltype=item.get("type"))
                if "create" in item:
                    vol = pool.create_volume(vol_name, item["size"], overwrite=overwrite, voltype=item.get("type"))
                disk_path = vol.path
                disk_type = vol.device
                driver_type = vol.format
            elif "dev" in item:
                disk_path = item["dev"]
                disk_type = "block"
                driver_type = "raw"
            elif "file" in item and hypervisor == "kvm":
                disk_path = item["file"]
                disk_type = "file"
                driver_type = item.get("driver", "qcow2")
            elif "source" in item and hypervisor == "lxc":
                disk_path = item["source"]
            else:
                raise LVPError("Unrecognized disk specification {0!r}".format(item))
            if disk_type == "block":
                dsource = XMLE.source(dev=disk_path)
            else:
                dsource = XMLE.source(file=disk_path)
            if disk_type == "block" or hypervisor == "kvm":
                devs.append(XMLE.disk(dsource,
                    XMLE.driver(name="qemu", type=driver_type, cache=item.get("cache", "none")),
                    XMLE.target(dev=dev_name)))
            elif hypervisor == "lxc":
                if not target_dir:
                    target_dir = "/" if i == 0 else "/disk{0}".format(i)
                devs.append(XMLE.filesystem(
                    XMLE.source(dir=disk_path),
                    XMLE.target(dir=target_dir),
                    type="mount", accessmode="passthrough"))

        # Set up interfaces - any hardware.nicX entries in spec,
        default_network = spec.get("default_network", "default")
        items = gethw("nic") or [{}]
        for i, item in enumerate(items):
            if "bridge" in item:  # support for old style bridge-only defs
                itype = "bridge"
                inet = item["bridge"]
            else:
                itype = item.get("type", "network")
                inet = item.get("network", default_network)
            iface = XMLE.interface(XMLE.mac(address=item.get("mac", macaddr(i))), type=itype)
            if hypervisor == "kvm":
                iface.append(XMLE.model(type="virtio"))
            if itype == "network":
                iface.append(XMLE.source(network=inet))
            elif itype == "bridge":
                iface.append(XMLE.source(bridge=inet))
            devs.append(iface)

        new_desc = etree.tostring(desc)
        vm = self.conn.defineXML(new_desc)
        self.libvirt_retry(vm.create)
        for retry in range(1, 10):
            self.refresh_list()
            if name in self.dominfo.vms:
                break
            time.sleep(2.0)
            self.log.info("waiting for VM {0} to appear in libvirt hosts... retry #{1}".format(name, retry))
        else:
            raise LVPError("VM {0} did not appear in time on libvirt hosts".format(name))

        return self.dominfo.vms[name]

    def libvirt_retry(self, op):
        """
        Workaround transient recoverable errors produced by libvirt.
        """
        end_time = time.time() + 30.0
        ignore = [
            # libvirt connection closed for some reason, just retry
            "Unable to read from monitor: Connection reset by peer",
            # lxc container starting often fails as they're started
            # simultaneously with the same device names, use a unique
            # name to work around it.
            # http://www.redhat.com/archives/libvir-list/2013-August/msg01475.html
            "RTNETLINK answers: File exists",
            ]
        while True:
            try:
                return op()
            except libvirt.libvirtError as error:
                if not any(ignorable in str(error) for ignorable in ignore):
                    # some other error, raise immediately
                    raise

                time_left = max(end_time - time.time(), 0)
                if not time_left:
                    # timeout
                    raise

                self.log.warning("got possibly transient error '%s' from libvirt, retrying for %.1fs...",
                                 error, time_left)
                time.sleep(1.0)


class PoniLVVol(object):
    def __init__(self, vol, pool):
        self.vol = vol
        self.pool = pool
        self.path = vol.path()
        self.format = None
        self.device = None
        self.__read_desc()

    def __read_desc(self):
        xml = etree.fromstring(self.vol.XMLDesc(0))
        format = xml.find("target").find("format")
        tformat = format.get("type") if format is not None else None
        self.format = tformat if tformat is not None else "raw"
        sdevice = xml.find("source").find("device")
        self.device = "block" if sdevice is not None else "file"


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
            "capacity": vals[1] / (1024 * 1024),
            "used": vals[2] / (1024 * 1024),
            "free": vals[3] / (1024 * 1024),
        }

    def _define_volume(self, target, megabytes, source, overwrite, voltype):
        name = "auto.{0}".format(target)
        # get source volume and its type if any
        if source:
            srcvol = self.pool.storageVolLookupByName(source)
            srctree = etree.fromstring(srcvol.XMLDesc(0))
            srctype = srctree.find("target").find("format").get("type")
        else:
            srcvol = None
            srctype = None
        # default to the same format as source or raw volumes on lvm and qcow2 elsewhere
        if not voltype:
            if srcvol:
                voltype = srctype
            elif self.type == "logical":
                voltype = "raw"
            else:
                voltype = "qcow2"
        # add a type suffix to file based volumes
        if self.type == "dir" and voltype in ("raw", "qcow2"):
            name = "{0}.{1}".format(name, voltype)
        voltree = XMLE.volume(
            XMLE.name(name),
            XMLE.target(XMLE.format(type=voltype)))
        bytes = (megabytes or 0) * 1024 * 1024
        if srcvol:
            if not bytes:
                bytes = srcvol.info()[1]
            voltree.append(XMLE.backingStore(
                    XMLE.format(type=srctype),
                    XMLE.path(srcvol.path())))
        voltree.append(XMLE.capacity(str(bytes)))
        volxml = etree.tostring(voltree)

        try:
            vol = self.pool.createXML(volxml, 0)
        except libvirt.libvirtError as ex:
            if not re.search("storage vol( '.*?')? already exists", str(ex)):
                raise
            if not overwrite:
                raise LVPError("{0!r} volume already exists".format(name))
            self.delete_volume(name)
            vol = self.pool.createXML(volxml, 0)

        return PoniLVVol(vol, self)

    def create_volume(self, target, megabytes, overwrite=False, voltype=None):
        return self._define_volume(target, megabytes, None, overwrite, voltype)

    def clone_volume(self, source, target, megabytes=None, overwrite=False, voltype=None):
        return self._define_volume(target, megabytes, source, overwrite, voltype)

    def delete_volume(self, name):
        self.pool.storageVolLookupByName(name).delete(0)

    def __read_desc(self):
        xml = etree.fromstring(self.pool.XMLDesc(0))
        self.type = xml.get("type")
        tpath = xml.find("target").find("path")
        self.path = tpath.text if tpath is not None else ""


class PoniLVDom(object):
    def __init__(self, conn, dom):
        self.log = logging.getLogger("poni.libvirt.dom")
        self.conn = conn
        self.dom = dom
        self.name = dom.name()
        self.macs = []
        self.disks = []
        self.fss = []
        self.info = {}
        self.__dom_info()
        self.__read_desc()

    def ipv6_addr(self, prefix="fe80::"):
        return [mac_to_ipv6(prefix, mac) for mac in self.macs]

    @convert_libvirt_errors
    def delete(self):
        try:
            self.dom.destroy()
        except libvirt.libvirtError as ex:
            if "domain is not running" not in str(ex).lower():
                raise

        # lookup and delete storage
        for disk in self.disks:
            delete_ok = False
            delete_ex = []
            try:
                vol = self.conn.conn.storageVolLookupByPath(disk)
                vol.delete(0)
            except libvirt.libvirtError as ex:
                if ex.get_error_code() != libvirt.VIR_ERR_NO_STORAGE_VOL:
                    raise LVPError("{0!r}: deletion failed: {1!r}".format(disk, ex))

        # delete filesystems that come from known storage pools
        if self.fss:
            pools = [("/{0}/".format(pool.path.strip("/")), pool)
                     for pool in self.conn.dominfo.pools.itervalues()]
            for fs in self.fss:
                for pool_path, pool in pools:
                    if fs.startswith(pool_path):
                        pool.delete_volume(fs[len(pool_path):])

        # delete snapshots
        if self.conn.hypervisor != "lxc":
            for name in self.dom.snapshotListNames(0):
                self.remove_snapshot(name)

        self.dom.undefine()

    def __dom_info(self):
        keys = ("state", "maxmem", "memory", "cpus", "cputime")
        vals = self.dom.info()
        self.info = dict(zip(keys, vals))

    def __read_desc(self):
        xml = etree.fromstring(self.dom.XMLDesc(0))
        devs = xml.find("devices")
        if devs is not None:
            self.macs = [str(iface.find("mac").get("address"))
                         for iface in devs.iter("interface")]
            self.disks = [str(disk.find("source").get("file") or disk.find("source").get("dev"))
                          for disk in devs.iter("disk")]
            self.fss = [str(fs.find("source").get("dir"))
                        for fs in devs.iter("filesystem")]

    @convert_libvirt_errors
    @ignore_libvirt_errors("vm_online")
    def power_on(self):
        self.log.info("powering on %r", self.name)
        self.dom.create()

    @convert_libvirt_errors
    @ignore_libvirt_errors("vm_offline")
    def power_off(self):
        self.log.info("powering off %r", self.name)
        self.dom.destroy()

    @convert_libvirt_errors
    def create_snapshot(self, name, description=None, memory=False):
        if not name or "/" in name:
            raise LVPError("invalid snapshot name {0!r}".format(name))
        # XXX: libvirt can't (at version 0.9.12) remove disk-only snapshots at all so let's not create them
        if not memory:
            raise LVPError("disk-only snapshots are not supported in libvirt vms at the moment")
        self.log.info("creating %s snapshot %r for %r", "memory" if memory else "disk-only", name, self.name)
        flags = 0 if memory else libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY
        snapxml = etree.tostring(XMLE.domainsnapshot(
            XMLE.name(name),
            XMLE.description(description or _created_str())))
        self.dom.snapshotCreateXML(snapxml, flags)

    @convert_libvirt_errors
    @ignore_libvirt_errors("snapshot_not_found")
    def remove_snapshot(self, name):
        self.log.info("removing snapshot %r from %r", name, self.name)
        snap = self.dom.snapshotLookupByName(name, 0)
        snap.delete(0)

    @convert_libvirt_errors
    def revert_to_snapshot(self, name):
        self.log.info("reverting %r to %r by force", name, self.name)
        snap = self.dom.snapshotLookupByName(name, 0)
        self.dom.revertToSnapshot(snap, libvirt.VIR_DOMAIN_SNAPSHOT_REVERT_FORCE)


def mac_to_ipv6(prefix, mac):
    mp = mac.split(":")
    inv_a = int(mp[0], 16) ^ 2
    addr = "{0}{1:02x}{2:02x}:{3:02x}ff:fe{4:02x}:{5:02x}{6:02x}" \
           .format(prefix, inv_a, int(mp[1], 16), int(mp[2], 16),
                   int(mp[3], 16), int(mp[4], 16), int(mp[5], 16))
    name = socket.getnameinfo((addr, 22), socket.NI_NUMERICSERV | socket.NI_NUMERICHOST)
    return name[0]
