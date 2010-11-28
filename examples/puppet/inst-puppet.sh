#! /bin/sh

set -e

AWS_KEYPAIR="mel-aws-us-east-1-mac"
REPO="$HOME/tmp/puppet"

rm -rf $REPO

poni -d $REPO script -v <<EOF
init

add-node template/ec2-deb6
add-config template/ec2-deb6 hacks
set template\$ verify=bool:false

add-node software
set software\$ verify=bool:false
add-config software puppet-master-v1.0
add-config software puppet-agent-v1.0

add-node puppet/master -i template/ec2-deb6
add-config puppet/master puppet-master -i software/puppet-master-v1.0
set puppet/master cloud.provider=aws-ec2 cloud.region=us-east-1 cloud.image=ami-daf615b3 cloud.kernel=aki-6eaa4907 cloud.ramdisk=ari-42b95a2b cloud.type=m1.small cloud.key-pair=$AWS_KEYPAIR user=root

add-node nodes/demo/server{id:02} -c2 -i template/ec2-deb6
add-config nodes/demo/server puppet-agent -i software/puppet-agent-v1.0
set nodes/demo/server cloud.provider=aws-ec2 cloud.region=us-east-1 cloud.image=ami-daf615b3 cloud.kernel=aki-6eaa4907 cloud.ramdisk=ari-42b95a2b cloud.type=m1.small cloud.key-pair=$AWS_KEYPAIR user=root

EOF

cp ec2-deb6/* $REPO/system/template/ec2-deb6/config/hacks/
cp puppet-master/* $REPO/system/software/config/puppet-master-v1.0/
cp puppet-agent/* $REPO/system/software/config/puppet-agent-v1.0/

# NOTE: verify cannot be run until hardware has been provisioned and
#       network addresses have been updated


