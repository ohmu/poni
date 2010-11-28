-- Hello from $node.name (parent system: $node.system.name)

-- I'm a DB node, but I know that there are $get_system("frontend$").sub_count frontends:
#for $fe in $find("frontend")
--  * frontend $fe.name at address $fe.host $edge($node.name, $fe.name, protocol="http")
#end for
