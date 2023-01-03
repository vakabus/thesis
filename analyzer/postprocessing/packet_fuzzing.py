from scapy.all import *
import sys
import json
from pydantic import BaseModel
import pandas as pd
from matplotlib import pyplot as plt

class Stats(BaseModel):
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


if len(sys.argv) == 1:
    print("missing argument - name of input csv")
    exit(1)

scapy_cap = PcapReader(sys.argv[1])
stats = []
cnt = 0
for pkt in scapy_cap:
    if pkt.haslayer(UDP) and pkt.haslayer(Raw):
        data = pkt.getlayer(Raw).load
        try:
            s = Stats.parse_raw(data.decode('utf8'))
            s.packets_before = cnt
            stats.append(s)
            cnt = 0
        except e:
            print(e)
    else:
        cnt += 1



df = pd.DataFrame([s.__dict__ for s in stats])

plt.plot(df['ms_since_start'], df['flows'], label="number of flows")
plt.scatter(df['ms_since_start'], df['packets_before'], label="packets send before the log event")

plt.legend()

plt.tight_layout()

plt.xlabel("ms since logging start")
plt.ylabel("count")

plt.show()