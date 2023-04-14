import sys
from matplotlib import pyplot as plt
import glob
import numpy as np
import polars as pl
from parsing import normalize_ts, parse_icmp_rtt, parse_trace, parse_udp_rr, parse_vswitchd, remove_offset_and_scale


if len(sys.argv) == 1:
    print("missing argument - name of input csv")
    exit(1)


d = sys.argv[1]
print(f"Source data: {d}")
trace_table, trace_cmd, trace_upcalls, trace_upcalls_filtered = parse_trace(glob.glob(f"{d}/kernel_flow_table_trace_*")[0])
vswitchd = parse_vswitchd(glob.glob(f"{d}/vswitchd*.csv")[0])
udp_rtt_latencies, udp_rtt_dropped = parse_udp_rr(glob.glob(f"{d}/udp_rr*csv")[0])
icmp_lat, icmp_err = parse_icmp_rtt(glob.glob(f"{d}/icmp_rtt*.csv")[0])

trace_table, trace_cmd, trace_upcalls, trace_upcalls_filtered, vswitchd, udp_rtt_latencies, udp_rtt_dropped, icmp_lat, icmp_err = normalize_ts(trace_table, trace_cmd, trace_upcalls, trace_upcalls_filtered, vswitchd, udp_rtt_latencies, udp_rtt_dropped, icmp_lat, icmp_err)
vswitchd, = remove_offset_and_scale('vswitchd_utime_sec', 1, vswitchd)
vswitchd, = remove_offset_and_scale('vswitchd_stime_sec', 1, vswitchd)
random_data = np.random.rand(len(trace_upcalls))* (-5000) - 1000


print("Data loading finished, rendering plots...")


# figure based on time
fig = plt.figure("time")
ax: plt.Axes = fig.subplots()
ax.scatter(trace_upcalls['ts'], random_data, label="upcalls (y-value does not mean anything)", marker=".", color="red", alpha=0.1)
#ax.scatter(vswitchd["ts"], vswitchd["vswitchd_threads"] * 10000, label="vswitchd threads * 10000", color="green", marker=".")
#ax.scatter(vswitchd["ts"], vswitchd["vswitchd_rss_bytes"] / 10240, label="vswitchd rss in 10KiB)", marker=".", color="orange")
ax.plot(trace_table['ts'], trace_table['flows'], label="flow table size")
#ax.plot(vswitchd["ts"], vswitchd["vswitchd_utime_sec"]*10000, label="vswitchd utime in 0.1ms", alpha=0.5)
#ax.plot(vswitchd["ts"], vswitchd["vswitchd_stime_sec"]*10000, label="vswitchd stime in 0.1ms", alpha=0.5)
ax.hlines([0], [0], [trace_table['ts'].tail(1).item()], linestyles="dotted", colors="black")

# UDP packets
ax.scatter(udp_rtt_latencies["ts"], udp_rtt_latencies["latency_ns"] / 100_000, label="UDP packet latency in 0.1ms", marker=".", color="green", alpha=0.5)
ax.hlines(udp_rtt_latencies["latency_ns"] / 100_000, udp_rtt_latencies['ts'], udp_rtt_latencies['ts'] + udp_rtt_latencies['latency_ns'].cast(pl.Float64) / 1_000_000_000, color="green", alpha=0.1)
ax.scatter(udp_rtt_dropped["ts"], udp_rtt_dropped["ts"]*0 - 7_000, label="dropped UDP packets", marker="o", color="green", alpha=0.5)

# ICMP
ax.scatter(icmp_lat["ts"], icmp_lat["latency_ns"] / 100_000, label="ICMP latency in 0.1ms (ping cmd)", marker=".", color="purple", alpha=0.5)
ax.hlines(icmp_lat["latency_ns"] / 100_000, icmp_lat['ts'], icmp_lat['ts'] + icmp_lat['latency_ns'].cast(pl.Float64) / 1_000_000_000, color="purple", alpha=0.1)
ax.scatter(icmp_err["ts"], icmp_err["ts"] * 0 - 8_000, label="ping cmd error", marker="o", color="purple", alpha=0.5)

ax.legend(loc='upper right')
fig.tight_layout()
ax.set_xlabel("sec")

"""
fig = plt.figure("resources")
ax: plt.Axes = fig.subplots()
ax.scatter(vswitchd["ts"], vswitchd["vswitchd_threads"], label="vswitchd threads")
ax.legend()
fig.tight_layout()
ax.set_xlabel("ns (CLOCK_MONOTONIC)")
ax.set_ylabel("count")
"""


plt.show()