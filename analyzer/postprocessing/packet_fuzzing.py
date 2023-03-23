from scapy.all import *
import sys
import json
from pydantic import BaseModel
import pandas as pd
from matplotlib import pyplot as plt
import glob
import numpy as np
from window import rolling_window_left

class Pkt(BaseModel):
    packets_before: int = 0
    tcpdump_time: float = 0


class Tag(Pkt):
    tag: str


class Stats(Pkt):
    ns_monotonic: int
    lookup_hit: int
    lookup_missed: int
    lookup_lost: int
    flows: int
    masks_hit: int
    masks_total: int
    masks_hit_per_pkt: float
    cache_hit: int
    cache_hit_rate: float
    cache_masks_size: int

    packets_before: int = 0
    tcpdump_time: EDecimal | float = 0.0
    delta_cache_hit: int = -1
    lookup_total: int = -1
    delta_lookups: int = -1
    delta_mask_hits: int = -1


if len(sys.argv) == 1:
    print("missing argument - name of input csv")
    exit(1)

def parse_pcap(filename: str) -> Tuple[pd.DataFrame, List[Tag]]:
    T = TypeVar("T", bound=Pkt)
    def try_parse(cls: Type[T], pkt: Packet) -> Optional[T]:
        data = bytes(pkt[UDP].payload)
        try:
            res = cls.parse_raw(data.decode('utf8'))
            res.tcpdump_time = pkt.time
            return res
        except Exception as e:
            return None


    # load
    scapy_cap = PcapReader(filename)
    stats: list[Stats] = []
    tags: list[Tag] = []
    cnt = 0
    for pkt in scapy_cap:
        if pkt.haslayer(UDP):
            s = try_parse(Stats, pkt)
            if s is not None:
                s.packets_before = cnt
                cnt = 0
                stats.append(s)
                continue
            
            s = try_parse(Tag, pkt)
            if s is not None:
                tags.append(s)
                continue

        else:
            cnt += 1


    # normalize time
    min_time = min([*tags, *stats], key=lambda p: p.tcpdump_time).tcpdump_time
    for t in tags:
        t.tcpdump_time -= min_time
    for s in stats:
        s.tcpdump_time -= min_time

    # calculate custom values
    for st in stats:
        st.lookup_total = st.lookup_missed + st.lookup_lost + st.lookup_hit

    # calculate deltas and other custom values
    for i,j in zip(range(len(stats)), range(1, len(stats))):
        stats[j].delta_cache_hit = stats[j].cache_hit - stats[i].cache_hit
        stats[j].delta_lookups = stats[j].lookup_total - stats[i].lookup_total
        stats[j].delta_mask_hits = stats[j].masks_hit - stats[i].masks_hit

    # convert to pandas frame
    return pd.DataFrame([s.__dict__ for s in stats]), tags


def parse_trace(filename: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trace = pd.read_json(path_or_buf=filename, lines=True, dtype={"ts": int})

    cmd_change = {
        "CMD_NEW": lambda s: s + 1,
        "CMD_DEL": lambda s: s - 1,
        "CMD_SET": lambda s: s,
    }

    table_change = {
        "TABLE_FLUSH": lambda s: 0,
        "TABLE_REMOVE": lambda s: s - 1,
        "TABLE_INSERT": lambda s: s + 1,
    }

    def create_row(ts, flows):
        return {"ts": ts, "flows": flows}

    def process(vtable):
        n_flows = 0
        data = []
        for _,row in trace.iterrows():
            data.append(create_row(ts=row["ts"]-1, flows=n_flows))
            if row["event"] in vtable:
                n_flows = vtable[row["event"]](n_flows)
            data.append(create_row(ts=row["ts"], flows=n_flows))

        return pd.DataFrame(data)


    upcalls = trace[(trace["event"]) == "UPCALL"]
    #res = []
    #window = 1_000_000_000  # ns
    #for ts, values in rolling_window_left(list(upcalls["ts"]), list(upcalls["event"]), window):
    #    res.append({'ts': ts + window, 'upcalls': len(values)})
    #upcalls = pd.DataFrame(res)

    return (process(table_change), process(cmd_change), upcalls)

def parse_tags(filename: str) -> pd.DataFrame:
    return pd.read_json(path_or_buf=filename, lines=True, dtype={"ts": int})

def parse_dpctl_dump(filename: str) -> pd.DataFrame:
    return pd.read_csv(filename)


print(f"Source data: {sys.argv[1]}")
d = sys.argv[1]
trace_table, trace_cmd, trace_upcalls = parse_trace(glob.glob(f"{d}/kernel_flow_table_trace_*.jsonl")[0])
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
upcalls_per_type = trace_upcalls.groupby("bin", sort=False).count()


# bar chart
fig = plt.figure("tests")
ax: plt.Axes = fig.subplots()
pos = np.arange(len(upcalls_per_type))
ax.bar(pos, upcalls_per_type['ts'], align='center', alpha=0.5, label="upcalls during measurements") # the ['ts'] does not matter, it all contains count
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