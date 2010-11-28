-- id: $node.name
-- this is db node $node.index and there are $system.sub_count nodes.
-- the system has $system.shards shards, so...
#set $start = $node.index * $system.shards / $system.sub_count
#set $end = ($node.index + 1) * $system.shards / $system.sub_count
-- I should be handling shards from $start to $end-1.

#for $shard in $range($start, $end)
CREATE TABLE data_${str(shard).zfill(3)} (a INT, b TEXT);
#end for

