#! /bin/sh

set -e

REPO="/tmp/example-db-cluster"
CONF_FILES="plugin.py tables.sql tables2.sql"
SETTINGS=""
REPORTS="report.txt network.dot"

rm -rf $REPO

echo create system

poni -d $REPO script <<EOF
init
add-node template/db-node
add-config template/db-node sql-shard
set template\$ verify=bool:false

# create db backend cluster
add-node db/backend/cluster/pg{id:04} -n 4 -i ^template/db-node\$
set db/backend/cluster\$ shards=int:64
set cluster/pg000 deploy=local

# create report node
add-node report/example
add-config report/example example1
set ^report/example deploy=local

# create some dummy frontend nodes
add-node web/frontend/leiska{id:02} -n 2
set frontend$ msg=hello-world
set leiska01 host=leiska01.company.com
set leiska02 host=leiska02.company.com

EOF

cp $CONF_FILES "$REPO/system/template/db-node/config/sql-shard/"
#cp $SETTINGS "$REPO/system/template/db-node/config/sql-shard/settings/"

cp $REPORTS "$REPO/system/report/example/config/example1/"
cp report_plugin.py "$REPO/system/report/example/config/example1/plugin.py"

echo verify and deploy
poni -d $REPO script <<EOF
verify
deploy
audit --diff

EOF




