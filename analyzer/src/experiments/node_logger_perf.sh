#!/bin/bash

_forward_sigint() { 
  echo "Caught SIGINT signal! Forwarding!" 
  kill -INT $(pgrep perf) 2>/dev/null
}

trap _forward_sigint SIGINT


pid="$(pgrep ovs-vswitchd)"
ns="nsenter -m -t $pid"
ns=""
$ns perf buildid-cache --add $($ns command -v ovs-vswitchd)
if $ns test -e /usr/lib64/libofproto.so; then
  $ns perf buildid-cache --add /usr/lib64/libofproto.so
fi
#$ns perf probe --del '*'
#$ns perf probe --add=sdt_udpif_revalidator:\* --add=sdt_revalidate:\*
$ns perf record -s -T -F 2000 --call-graph dwarf,8196 -p $pid -o out.perf -k CLOCK_MONOTONIC -e cycles &
child=$! 
wait "$child" # this will be interrupted by the signal
wait "$child"

# bundle all binaries
$ns perf archive out.perf
$ns tar -jcv out.perf out.perf.tar.bz2 -f result.perf.tar.bz2
$ns rm out.perf
$ns rm out.perf.tar.bz2

# copy out of the container
# root=$(cat /proc/$pid/mounts | grep -o upperdir=[^,]* | sed 's/upperdir=//')
# cp $root/result.perf.tar.bz2 $1
cp result.perf.tar.bz2 $1

# clean data from the container
$ns rm result.perf.tar.bz2
