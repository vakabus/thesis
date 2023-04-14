from scapy.all import *
import sys
import json
import pandas as pd
from matplotlib import pyplot as plt
import glob
import numpy as np
from window import rolling_window_left

from parsing import parse_trace, parse_tags, parse_dpctl_dump, parse_pcap




if len(sys.argv) == 1:
    print("missing argument - name of input csv")
    exit(1)




d = sys.argv[1]
print(f"Source data: {d}")
trace_table, trace_cmd, trace_upcalls, trace_upcalls_filtered = parse_trace(glob.glob(f"{d}/kernel_flow_table_trace_*")[0])
#packets_hist = parse_pcap(glob.glob(f"{d}/packet_capture_*.pcap")[0])
tags = parse_tags(glob.glob(f"{d}/tags*.jsonl")[0])
dpctl_log = parse_dpctl_dump(glob.glob(f"{d}/log_ovs_dpctl_show*.csv")[0])




# figure based on time
fig = plt.figure("time")
ax: plt.Axes = fig.subplots()
ax.plot(trace_table['ts'], trace_table['flows'], label="flow table size")
ax.scatter(trace_upcalls['ts'], trace_upcalls['ts']*0, label="upcalls")
ax.vlines(tags["ts"], 0, 900, linestyles="dotted", colors="red")
for _,t in tags.iterrows():
    ax.text(t.ts, 5, t.tag, rotation = 90, bbox=dict(boxstyle="round", ec=(1., 0.5, 0.5),fc=(1., 0.8, 0.8)))
ax.legend()
fig.tight_layout()
ax.set_xlabel("ns (CLOCK_MONOTONIC)")
ax.set_ylabel("count")


# bar chart processing
trace_upcalls['bin'] = pd.cut(trace_upcalls['ts'], bins=tags['ts'], labels=tags['tag'][:-1], ordered=False)
trace_upcalls = trace_upcalls[~trace_upcalls['bin'].isnull()]
upcalls_per_type = trace_upcalls.groupby("bin", sort=True).count()

trace_upcalls_filtered['bin'] = pd.cut(trace_upcalls_filtered['ts'], bins=tags['ts'], labels=tags['tag'][:-1], ordered=False)
trace_upcalls_filtered = trace_upcalls_filtered[~trace_upcalls_filtered['bin'].isnull()]
upcalls_per_type_filtered = trace_upcalls_filtered.groupby("bin", sort=True).count()


# bar chart
fig = plt.figure("tests")
ax: plt.Axes = fig.subplots()
pos = np.arange(len(upcalls_per_type))
ax.bar(pos, upcalls_per_type['ts'], align='center', alpha=0.5, label="all upcalls during measurements") # the ['ts'] does not matter, it all contains count
ax.bar(pos, upcalls_per_type_filtered['ts'], align='center', alpha=0.5, label="upcalls during measurements (direct cause was us)") # the ['ts'] does not matter, it all contains count
ax.set_xticks(pos, upcalls_per_type.index, rotation='vertical')
ax.legend()
ax.set_ylabel("number of upcalls")
ax.hlines(1000, xmin=0, xmax=len(upcalls_per_type), linestyles="dotted", color="red")




# plot
#plt.plot(dpctl_log['ns_monotonic'], dpctl_log['flows'], label="dumped flows")
#plt.plot(trace_cmd['ts'], trace_cmd['flows'], label="cmd traced flows")
#plt.plot(df["ns_monotonic"], df["delta_cache_hit"] / df["packets_before"], label="instant cache hit rate")
#plt.plot(df["ns_monotonic"], df["delta_mask_hits"] / df["delta_lookups"], label="instant masks hit per pkt")
#plt.scatter(df['ns_monotonic'], df['packets_before'], label="packets send before the log event")
#plt.scatter(df['ns_monotonic'], df['delta_lookups'], label="delta lookups")
#plt.scatter(df["ns_monotonic"], df["masks_hit_per_pkt"], label="masks hit per pkt")






plt.show()