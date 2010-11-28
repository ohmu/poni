#! /bin/sh

set -e

# make upgrades quiet
export DEBIAN_FRONTEND=noninteractive
echo force-confold >> /etc/dpkg/dpkg.cfg
echo force-confdef >> /etc/dpkg/dpkg.cfg

# upgrade
apt-get update

set +e
# this will fail...
apt-get --yes dist-upgrade
set -e

# ...fix (hack) the failed upgrade and retry
mv /etc/init.d/ec2* /root/
apt-get --yes -f install
apt-get --yes dist-upgrade

# add software
apt-get --yes install ack-grep less
