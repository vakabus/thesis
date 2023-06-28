from scapy.all import *
import sys
import json
import pandas as pd
import polars as pl
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
for tag, ts in tags.iter_rows():
    ax.text(ts, 5, tag, rotation = 90, bbox=dict(boxstyle="round", ec=(1., 0.5, 0.5),fc=(1., 0.8, 0.8)))
ax.legend()
fig.tight_layout()
ax.set_xlabel("ns (CLOCK_MONOTONIC)")
ax.set_ylabel("count")


# bar chart processing
trace_upcalls = trace_upcalls.with_columns(
    trace_upcalls['ts'].cut(bins=tags['ts'], labels=["junk"]+list(tags['tag']), maintain_order=True, category_label='test')['test'].cast(str)
).filter(~pl.col("test").is_in(("junk", "end")))
upcalls_per_type = trace_upcalls.groupby("test", maintain_order=True).count().join(tags, left_on="test", right_on="tag", how="outer").filter(~pl.col("test").is_in(("junk", "end"))).sort("count", descending=True)

trace_upcalls_filtered = trace_upcalls_filtered.with_columns(
    trace_upcalls_filtered['ts'].cut(bins=tags['ts'], labels=["junk"]+list(tags['tag']), maintain_order=True, category_label='test')['test'].cast(str)
).filter(~pl.col("test").is_in(("junk", "end")))
upcalls_per_type_filtered = trace_upcalls_filtered.groupby("test", maintain_order=True).count().join(tags, left_on="test", right_on="tag", how="outer").filter(~pl.col("test").is_in(("junk", "end")))

print("difference between the sets")
print(set(upcalls_per_type['test']).symmetric_difference(set(upcalls_per_type_filtered['test'])))


# bar chart
fig = plt.figure("tests", figsize=(10, 18), dpi=600)
ax: plt.Axes = fig.subplots()
pos = list(reversed(range(len(upcalls_per_type))))
ax.barh(pos, upcalls_per_type['count'], align='center', alpha=0.5, label="number of upcalls during the time slot")
#ax.bar(pos, upcalls_per_type_filtered['count'], align='center', alpha=0.5, label="upcalls during measurements (direct cause was us)")
ax.set_yticks(pos, upcalls_per_type["test"])
ax.legend()
ax.set_xlabel("number of upcalls")
ax.vlines(1000, ymin=0, ymax=len(upcalls_per_type), linestyles="dotted", color="red")




# plot
#plt.plot(dpctl_log['ns_monotonic'], dpctl_log['flows'], label="dumped flows")
#plt.plot(trace_cmd['ts'], trace_cmd['flows'], label="cmd traced flows")
#plt.plot(df["ns_monotonic"], df["delta_cache_hit"] / df["packets_before"], label="instant cache hit rate")
#plt.plot(df["ns_monotonic"], df["delta_mask_hits"] / df["delta_lookups"], label="instant masks hit per pkt")
#plt.scatter(df['ns_monotonic'], df['packets_before'], label="packets send before the log event")
#plt.scatter(df['ns_monotonic'], df['delta_lookups'], label="delta lookups")
#plt.scatter(df["ns_monotonic"], df["masks_hit_per_pkt"], label="masks hit per pkt")


fig.savefig('/tmp/plot.pdf', bbox_inches="tight")



#plt.show()