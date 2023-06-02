#!/bin/bash

caught_signal=false

_forward_sigint() { 
  echo "Caught SIGINT signal! Forwarding!" 
  kill -INT $(pgrep bpftrace) 2>/dev/null
  caught_signal=true
}

trap _forward_sigint SIGINT

# write CSV header
echo "ts;flow_limit;duration_ns;flows;probe;tid" > $1

while ! $caught_signal; do
    pid=$(pgrep ovs-vswitchd)
    ts="\$ts" # hack to get rid of escaping needs

    cat <<EOF > /tmp/usdt.bt
        usdt:/proc/$pid/root/usr/sbin/ovs-vswitchd:udpif_revalidator:new_flow_limit {
            printf("%lld;%lld;%lld;%lld;new_flow_limit;%lld\n", nsecs, arg0, arg1*1000000, arg2, tid);
        }

        usdt:/proc/$pid/root/usr/sbin/ovs-vswitchd:udpif_revalidator:barrier_first_entry {
            @first[tid] = nsecs;
        }

        usdt:/proc/$pid/root/usr/sbin/ovs-vswitchd:udpif_revalidator:barrier_first_exit {
            $ts = nsecs;
            printf("%lld;0;%lld;0;barrier_first_exit;%lld\n", $ts, $ts - @first[tid], tid);
            delete(@first[tid]);
        }

        usdt:/proc/$pid/root/usr/sbin/ovs-vswitchd:udpif_revalidator:barrier_second_entry {
            @second[tid] = nsecs;
        }

        usdt:/proc/$pid/root/usr/sbin/ovs-vswitchd:udpif_revalidator:barrier_second_exit {
            $ts = nsecs;
            printf("%lld;0;%lld;0;barrier_second_exit;%lld\n", $ts, $ts - @second[tid], tid);
            delete(@second[tid]);
        }

        usdt:/proc/$pid/root/usr/sbin/ovs-vswitchd:udpif_revalidator:barrier_third_entry {
            @third[tid] = nsecs;
        }

        usdt:/proc/$pid/root/usr/sbin/ovs-vswitchd:udpif_revalidator:barrier_third_exit {
            $ts = nsecs;
            printf("%lld;0;%lld;0;barrier_third_exit;%lld\n", $ts, $ts - @third[tid], tid);
            delete(@third[tid]);
        }

        usdt:/proc/$pid/root/usr/sbin/ovs-vswitchd:udpif_revalidator:waiting_block_entry {
            @block[tid] = nsecs;
        }

        usdt:/proc/$pid/root/usr/sbin/ovs-vswitchd:udpif_revalidator:waiting_block_exit {
            $ts = nsecs;
            printf("%lld;0;%lld;0;waiting_block_exit;%lld\n", $ts, $ts - @block[tid], tid);
            delete(@block[tid]);
        }
EOF

        # kfunc:openvswitch:ovs_lock {
        #     @ovslock[tid] = nsecs;
        # }
        # 
        # kfunc:openvswitch:ovs_unlock {
        #     $ts = nsecs;
        #     printf("%lld;0;%lld;0;ovs_unlock;%lld\n", $ts, $ts - @ovslock[tid], tid);
        #     delete(@ovslock[tid]);
        # }
        # 
        # 
        # 
        # kprobe:mutex_lock / @should[tid] == 1 / {
        #     @lock[tid] = nsecs;
        # }
        # 
        # kprobe:mutex_unlock / @should[tid] == 1 && @lock[tid] != 0 / {
        #     $ts = nsecs;
        #     printf("%lld;0;%lld;0;ovs_unlock;%lld\n", $ts, $ts - @lock[tid], tid);
        #     delete(@lock[tid]);
        # }
        # 
        # kprobe:ovs_flow_cmd_new {
        # 	@should[tid] = 1;
        # }
        # 
        # kretprobe:ovs_flow_cmd_new {
        # 	delete(@should[tid]);
        # }
        # 
        # kprobe:ovs_flow_cmd_del {
        # 	@should[tid] = 1;
        # }
        # 
        # kretprobe:ovs_flow_cmd_del {
        # 	delete(@should[tid]);
        # }
        # 
        # kprobe:ovs_flow_cmd_dump {
        # 	@should[tid] = 1;
        # }
        # 
        # kretprobe:ovs_flow_cmd_dump {
        # 	delete(@should[tid]);
        # }
# EOF

    echo "Monitoring ovs-vswitchd USDT probes..."
    bpftrace -p $pid /tmp/usdt.bt | grep -v "Attaching" | head -n -2 | grep -v @ | grep '[^[:blank:]]' >> $1 &
    child=$! 
    wait "$child" # this will be interrupted by the signal

    # if ovs-vswitchd crashes, we want to keep monitoring what happens
    if ! $caught_signal; then
        echo "ovs-vswitchd crashed!"
        while ! pgrep ovs-vswitchd > /dev/null; do
            sleep 0.25
        done
    fi
done
wait "$child"

echo "Monitoring finished. Dump in $1"