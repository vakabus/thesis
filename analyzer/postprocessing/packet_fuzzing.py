from scapy.all import *
import sys
import json
from pydantic import BaseModel
import pandas as pd
from matplotlib import pyplot as plt

class Pkt(BaseModel):
    packets_before: int = 0
    tcpdump_time: float = 0


class Tag(Pkt):
    tag: str


class Stats(Pkt):
    ms_since_start: int
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


if len(sys.argv) == 1:
    print("missing argument - name of input csv")
    exit(1)

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
scapy_cap = PcapReader(sys.argv[1])
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

# convert to pandas frame
df = pd.DataFrame([s.__dict__ for s in stats])


# plot
plt.plot(df['tcpdump_time'], df['flows'], label="number of flows")
plt.scatter(df['tcpdump_time'], df['packets_before'], label="packets send before the log event")

for t in tags:
    plt.text(t.tcpdump_time + 6, 5, t.tag, rotation = 90, bbox=dict(boxstyle="round", ec=(1., 0.5, 0.5),fc=(1., 0.8, 0.8)))

plt.legend()

plt.tight_layout()

plt.xlabel("seconds since logging start")
plt.ylabel("count")

plt.show()