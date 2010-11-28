node 'default' {
  notice 'no specific rules for node'
}

class nginx {
  package { nginx:
    ensure => latest
  }

#  service { nginx:
#    running => true
#  }
}

#for $agent in $find("demo")
node '$agent.private.dns.lower()' {
  # fscm node: $agent.name
  file { "/etc/sudoers":
      owner => root, group => root, mode => 440
  }

  include nginx
}
#end for
