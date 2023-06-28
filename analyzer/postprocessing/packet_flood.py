import sys
from matplotlib import pyplot as plt
import glob
import numpy as np
import polars as pl
from parsing import normalize_ts, parse_dpctl_dump, parse_icmp_rtt, parse_loadavg, parse_trace, parse_udp_rr, parse_usdt, parse_vswitchd, remove_offset_and_scale, renumber, window_frequency


if len(sys.argv) == 1:
    print("missing argument - name of the input directory")
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
ax, ax2, ax3 = fig.subplots(3, 1, sharex=True, height_ratios=(5,5,2))

# upcalls plot
fr = window_frequency(trace_upcalls, 0.1)

# resources
ax3.plot(vswitchd["ts"], vswitchd["vswitchd_rss_bytes"] / 2**30, label="ovs-vswitchd RSS GiB", color="green")
ax3.plot(loadavg["ts"], loadavg["loadavg1"], label="load average (1min)")


# latencies
# UDP packets
ax2.set_ylabel("ms")
ax2.set_yticks([0,2000,4000, 6000, 8000])
ax2.scatter(udp_rtt_latencies["ts"], udp_rtt_latencies["latency_ns"] / 1000000, label="UDP packet RTT", marker=".", color="green", alpha=0.5, linewidths=0)
ax2.hlines(udp_rtt_latencies["latency_ns"] / 1000000, udp_rtt_latencies['ts'], udp_rtt_latencies['ts'] + udp_rtt_latencies['latency_ns'].cast(pl.Float64) / 1_000_000_000, color="green", alpha=0.1, label="UDP packet in-flight time")
ax2.scatter(udp_rtt_dropped["ts"], udp_rtt_dropped["ts"]*0 - 1_000, label="dropped UDP packets", marker="x", color="green", alpha=0.5)
# ICMP
ax2.scatter(icmp_lat["ts"], icmp_lat["latency_ns"] / 1000000, label="ICMP RTT (ping cmd)", marker=".", color="purple", alpha=0.5, linewidths=0)
ax2.hlines(icmp_lat["latency_ns"] / 1000000, icmp_lat['ts'], icmp_lat['ts'] + icmp_lat['latency_ns'].cast(pl.Float64) / 1_000_000_000, color="purple", alpha=0.1, label="ICMP packet in-flight time")
ax2.scatter(icmp_err["ts"], icmp_err["ts"] * 0 - 2_000, label="ping cmd error", marker="x", color="purple", alpha=0.5)


# flow table
#ax.plot(trace_table['ts'], trace_table['flows'], label="flow table size")
ax.plot(fr['mts'], fr['freq'], label="upcalls per second (100ms window)", color="C1")
ax.plot(dpctl_log['ts'], dpctl_log['flows'], label="flow table size", color="C0")
ax.scatter(usdt_flow_limit['ts'], usdt_flow_limit['flow_limit'], label="flow limit (ovs-vswitchd)", color="C3", marker=".")
ax.hlines(usdt_flow_limit['flow_limit'][:-1], (usdt_flow_limit['ts'] - usdt_flow_limit['duration_ns'].cast(pl.Float64) / 1_000_000_000)[1:], usdt_flow_limit['ts'][1:], linewidth=0.5, color="C3", label="revalidator loop duration")


ax.legend(loc='upper right')
ax.set_ylim((-1000, 70_000))
ax2.legend(loc='upper left')
ax3.legend(loc='upper left')
#fig.tight_layout()

fig.subplots_adjust(hspace=0)


plt.savefig("/tmp/plot.pdf", bbox_inches="tight")
#plt.show()