import sys
from matplotlib import pyplot as plt
import glob
import numpy as np
import polars as pl
from parsing import normalize_ts, parse_dpctl_dump, parse_icmp_rtt, parse_loadavg, parse_trace, parse_udp_rr, parse_usdt, parse_vswitchd, remove_offset_and_scale, renumber, window_frequency


if len(sys.argv) != 3:
    print("missing argument: [name of input csv] [name of the output file]")
    exit(1)


d = sys.argv[1]
print(f"Source data: {d}")
trace_table, trace_cmd, trace_upcalls, trace_upcalls_filtered = parse_trace(glob.glob(f"{d}/kernel_flow_table_trace_*")[0])
vswitchd = parse_vswitchd(glob.glob(f"{d}/vswitchd*.csv")[0])
udp_rtt_latencies, udp_rtt_dropped = parse_udp_rr(glob.glob(f"{d}/udp_rr*csv")[0])
icmp_lat, icmp_err = parse_icmp_rtt(glob.glob(f"{d}/icmp_rtt*.csv")[0])
usdt_flow_limit, usdt_barriers, kernel_lock = parse_usdt(glob.glob(f"{d}/ovs-vswitchd-usdt*.csv")[0])
dpctl_log = parse_dpctl_dump(glob.glob(f"{d}/log_ovs_dpctl_show*.csv")[0])
loadavg = parse_loadavg(glob.glob(f"{d}/loadavg*.csv")[0])
trace_table, trace_cmd, trace_upcalls, trace_upcalls_filtered, vswitchd, udp_rtt_latencies, udp_rtt_dropped, icmp_lat, icmp_err, usdt_flow_limit, usdt_barriers, kernel_lock, dpctl_log, loadavg = normalize_ts(trace_table, trace_cmd, trace_upcalls, trace_upcalls_filtered, vswitchd, udp_rtt_latencies, udp_rtt_dropped, icmp_lat, icmp_err, usdt_flow_limit, usdt_barriers, kernel_lock, dpctl_log, loadavg)


print("Data loading finished, rendering plots...")


# figure based on time
fig = plt.figure("time", dpi=600, figsize=(13,8))
ax: plt.Axes
ax2: plt.Axes
ax3: plt.Axes
ax4: plt.Axes
ax, ax2, ax4 = fig.subplots(3, 1, sharex=True, height_ratios=(6,2,2))

# upcalls plot
fr = window_frequency(trace_upcalls, 0.1)

# resources
#ax2.scatter(vswitchd["ts"], vswitchd["vswitchd_threads"] * 10000, label="vswitchd threads * 10000", color="green", marker=".")
ax2.plot(vswitchd["ts"], vswitchd["vswitchd_rss_bytes"] / 2**20, label="ovs-vswitchd RSS in MiB", color="green")

ax4.plot(loadavg["ts"], loadavg["loadavg1"], label="load average (1min)")

# flow table size
#ax.plot(trace_table['ts'], trace_table['flows'], label="flow table size")
ax.plot(fr['mts'], fr['freq'], label="upcalls per second (100ms window)", color="C1")
ax.plot(dpctl_log['ts'], dpctl_log['flows'], label="flow table size (#entries)", color="C0")

ax.legend(loc='upper left')
ax2.legend(loc='upper left')
ax4.legend(loc='upper left')
#fig.tight_layout()
ax4.set_xlabel("seconds")

fig.subplots_adjust(hspace=0)


plt.savefig(sys.argv[2], bbox_inches="tight")
#plt.show()