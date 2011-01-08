#! /bin/bash -ue

# bootstrap puppet agent in a node

# make upgrades quiet
export DEBIAN_FRONTEND=noninteractive
echo force-confold >> /etc/dpkg/dpkg.cfg
echo force-confdef >> /etc/dpkg/dpkg.cfg

apt-get -q update

# add puppet master to /etc/hosts
#set $master = $get_node("example/master")
echo >> /etc/hosts
echo "# puppet master" >> /etc/hosts
echo "$master.private.ip $master.private.dns.lower() puppet" >> /etc/hosts

# install puppet agent
apt-get -q --yes --force-yes install puppet
perl -pi -e 's/START=no/START=yes/' /etc/default/puppet
/etc/init.d/puppet start

# debug command if you get "Could not retrieve catalog from remote server: hostname was not match with the server certificate":
# openssl s_client -connect $master.private.dns.lower():8140 -showcerts -showcerts > debug
