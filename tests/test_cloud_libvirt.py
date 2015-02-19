"""
tests for cloud_libvirt

XXX: just testing a couple of utility functions for now, implement a more
complete set of tests.
"""

from poni import cloud_libvirt

def test_parse_ip_addr():
    a = list(cloud_libvirt.parse_ip_addr(""))
    assert a == []

    a = list(cloud_libvirt.parse_ip_addr("1: foo\n2: bar"))
    assert a == [
        {'hardware-address': None, 'ip-addresses': [], 'name': 'foo'},
        {'hardware-address': None, 'ip-addresses': [], 'name': 'bar'},
        ]

    s = """
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
    inet6 ::1/128 scope host
       valid_lft forever preferred_lft forever
2: wwp0s20u4i6: <BROADCAST,MULTICAST,NOARP> mtu 1500 qdisc noop state DOWN group default qlen 1000
    link/ether 72:11:80:21:27:fb brd ff:ff:ff:ff:ff:ff
3: em1: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc pfifo_fast state DOWN group default qlen 1000
    link/ether 3c:97:0e:9d:7c:f5 brd ff:ff:ff:ff:ff:ff
4: wlp3s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000
    link/ether 6c:88:14:65:80:80 brd ff:ff:ff:ff:ff:ff
    inet 192.168.50.164/24 brd 192.168.50.255 scope global dynamic wlp3s0
       valid_lft 83510sec preferred_lft 83510sec
    inet6 fe80::6e88:14ff:fe65:8080/64 scope link
       valid_lft forever preferred_lft forever
5: virbr0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN group default
    link/ether 52:54:00:fb:be:ef brd ff:ff:ff:ff:ff:ff
    inet 192.168.232.1/24 brd 192.168.232.255 scope global virbr0
       valid_lft forever preferred_lft forever
    inet6 fe80::5054:ff:fefb:beef/64 scope link
       valid_lft forever preferred_lft forever
6: virbr0-nic: <BROADCAST,MULTICAST> mtu 1500 qdisc pfifo_fast master virbr0 state DOWN group default qlen 500
    link/ether 52:54:00:fb:be:ef brd ff:ff:ff:ff:ff:ff
"""
    a = list(cloud_libvirt.parse_ip_addr(s))
    assert len(a) == 6
    assert a[0] == {
        "name": "lo",
        "hardware-address": "00:00:00:00:00:00",
        "ip-addresses": [
            {"ip-address-type": "ipv4", "ip-address": "127.0.0.1", "prefix": 8},
            {"ip-address-type": "ipv6", "ip-address": "::1", "prefix": 128},
            ],
        }
    assert a[1] == {
        "name": "wwp0s20u4i6",
        "hardware-address": "72:11:80:21:27:fb",
        "ip-addresses": [],
        }
    assert a[2] == {
        "name": "em1",
        "hardware-address": "3c:97:0e:9d:7c:f5",
        "ip-addresses": [],
        }
    assert a[3] == {
        "name": "wlp3s0",
        "hardware-address": "6c:88:14:65:80:80",
        "ip-addresses": [
            {"ip-address-type": "ipv4", "ip-address": "192.168.50.164", "prefix": 24},
            {"ip-address-type": "ipv6", "ip-address": "fe80::6e88:14ff:fe65:8080", "prefix": 64},
            ],
        }
    assert a[4] == {
        "name": "virbr0",
        "hardware-address": "52:54:00:fb:be:ef",
        "ip-addresses": [
            {"ip-address-type": "ipv4", "ip-address": "192.168.232.1", "prefix": 24},
            {"ip-address-type": "ipv6", "ip-address": "fe80::5054:ff:fefb:beef", "prefix": 64},
            ],
        }
    assert a[5] == {
        "name": "virbr0-nic",
        "hardware-address": "52:54:00:fb:be:ef",
        "ip-addresses": [],
        }

def test_mac_to_ipv6():
    a = cloud_libvirt.mac_to_ipv6("fe80::", "52:54:00:fb:be:ef")
    assert a == "fe80::5054:ff:fefb:beef"
