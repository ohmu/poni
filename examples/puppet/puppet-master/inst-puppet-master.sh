#! /bin/bash -ue

# bootstrap puppet master in a node

# make apt-get upgrades quiet
export DEBIAN_FRONTEND=noninteractive
echo force-confold >> /etc/dpkg/dpkg.cfg
echo force-confdef >> /etc/dpkg/dpkg.cfg

apt-get -q --yes update

# install
perl -pi -e 's/(127.0.0.1.*)/\1 puppet/' /etc/hosts
apt-get install -q --yes --force-yes puppetmaster puppet

# wait until csr arrives...
# puppetca --list
# puppetca --sign ip-10-212-235-164.ec2.internal
