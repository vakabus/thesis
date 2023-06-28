import sys
from matplotlib import pyplot as plt
from matplotlib import patches as mpatches
import glob
import numpy as np
import polars as pl
from parsing import normalize_ts, parse_dpctl_dump, parse_icmp_rtt, parse_loadavg, parse_trace, parse_udp_rr, parse_usdt, parse_vswitchd, remove_offset_and_scale, renumber, window_frequency
from window import rolling_window_left


if len(sys.argv) == 1:
    print("missing argument - name of input csv")
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


STRESSED_INTERVAL = [12, 125]
NON_STRESSED_INTERVAL = [145, 239]
import numpy as np
import scipy.stats
def mean_confidence_interval(data, confidence=0.95):
    a = 1.0 * np.array(data)
    n = len(a)
    m, se = np.mean(a), scipy.stats.sem(a)
    h = se * scipy.stats.t.ppf((1 + confidence) / 2., n-1)
    return m, m-h, m+h
print("stressed UDP latency")
st = udp_rtt_latencies.filter(pl.col("ts").is_between(*STRESSED_INTERVAL))
print(st.describe())
print(mean_confidence_interval(st['latency_ns']))
print("non-stressed UDP latencies")
nst = udp_rtt_latencies.filter(pl.col("ts").is_between(*NON_STRESSED_INTERVAL))
print(nst.describe())
print(mean_confidence_interval(nst['latency_ns']))



print("Data loading finished, rendering plots...")


# figure based on time
# figure based on time
fig = plt.figure("time", dpi=600, figsize=(13,8))
ax: plt.Axes
ax2: plt.Axes
ax3: plt.Axes
ax, ax2, ax3 = fig.subplots(3, 1, sharex=True, height_ratios=(6, 1.5, 0.6))

# upcall frequency
fr = window_frequency(trace_upcalls, 0.1)
ax2.plot(fr['ts'] / 1000, fr['freq'], label="upcall frequency (window size 100ms)")
ax2.set_ylabel("Hz")
ax2.set_yticks([0, 25000, 50000])
ax2.set_ylim((0,60000))
ax2.legend(loc='upper right')

# RTTs
udp_rtt_latencies = udp_rtt_latencies.filter(pl.col("latency_ns") < 420_000 )
icmp_lat = icmp_lat.filter(pl.col("latency_ns") < 420_000 )
def median_line(df, lat, width):
    times = []
    medians = []
    q25 = []
    q75 = []
    wmin = []
    wmax = []
    for ts_left, values in rolling_window_left(df["ts"], df[lat], width):
        medians.append(np.median(values))
        wmin.append(np.quantile(values, 0.05))
        wmax.append(np.quantile(values, 0.95))
        q25.append(np.quantile(values, 0.25))
        q75.append(np.quantile(values, 0.75))
        times.append((ts_left + width/2))  # centered
    return times, medians, q25, q75, wmin, wmax

WINDOW = 2 # in micros
udp_rtt_latencies = udp_rtt_latencies.with_columns((pl.col("latency_ns") / 1000).alias("latency_us"))
icmp_lat = icmp_lat.with_columns((pl.col("latency_ns") / 1000).alias("latency_us"))
ts1, med1, q251, q751, min1, max1 = median_line(udp_rtt_latencies, "latency_us", WINDOW)
ts2, med2, q252, q752, min2, max2 = median_line(icmp_lat, "latency_us", WINDOW)

ax.fill_between(ts1, min1, max1, alpha=0.1, color="C0")
ax.fill_between(ts1, q251, q751, alpha=0.4, color="C0")
ax.plot(ts1, med1, label=f"centered {WINDOW}s-window median 1", color="C0")
ax.fill_between(ts2, min2, max2, alpha=0.1, color="C1")
ax.fill_between(ts2, q252, q752, alpha=0.4, color="C1")
ax.plot(ts2, med2, label=f"centered {WINDOW}s-window median 2", color="C1")
ax.scatter(udp_rtt_latencies["ts"], udp_rtt_latencies["latency_ns"] / 1_000, label="UDP packet RTT", linewidths=0, s=1, color="C0", alpha=0.8)
ax.scatter(icmp_lat["ts"], icmp_lat["latency_ns"] / 1_000, label="ICMP RTT (ping cmd)", linewidths=0, s=1, color="C1", alpha=0.8)
ax.set_ylabel("μs")
ax.set_xlabel("seconds")
ax.set_ylim((70, 300))

blue = mpatches.Patch(color='C0', label='UDP latencies')
orange = mpatches.Patch(color='C1', label='ICMP latencies')
description2 = mpatches.Patch(color='none', label=f"highlighed 5th, 25th, 50th, 75th and 95th percentiles")
description = mpatches.Patch(color='none', label=f"using {WINDOW}s-wide rolling window")
ax.legend(handles=[blue, orange, description2, description], loc="upper left")


# sample ranges
ax3.hlines(0, STRESSED_INTERVAL[0], STRESSED_INTERVAL[1], colors="C2", linestyles="solid", label="sample range for stressed data", linewidth=3)
ax3.hlines(0, NON_STRESSED_INTERVAL[0], NON_STRESSED_INTERVAL[1], colors="C3", linestyles="solid", label="sample ranges for non-stressed data", linewidth=3)
ax3.set_yticks([])
ax3.set_ylim((-1,6))
ax3.legend(handles=[mpatches.Patch(color='none', label="sample ranges for difference calculation")])

fig.subplots_adjust(hspace=0)

plt.savefig("/tmp/plot.pdf", bbox_inches="tight")
#plt.show()