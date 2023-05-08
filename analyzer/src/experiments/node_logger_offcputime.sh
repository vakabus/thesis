#!/bin/bash

# _forward_sigint() { 
#   echo "Caught SIGINT signal! Forwarding!" 
#   kill -INT $(pgrep offcputime) 2>/dev/null
# }
# 
# trap _forward_sigint SIGINT


pid="$(pgrep ovs-vswitchd)"

#exec /usr/share/bcc/tools/offcputime -K --stack-storage-size 8192 -f > $1
exec /usr/share/bcc/tools/offcputime -p $pid --stack-storage-size 8192 -f > $1