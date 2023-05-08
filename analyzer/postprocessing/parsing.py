
import polars as pl
from typing import List, Optional, Tuple, Type, TypeVar
from pydantic import BaseModel
from scapy import *


def parse_trace(filename: str) -> Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    # backwards compatible file loading
    if filename.endswith("csv"):
        trace = pl.read_csv(filename)
    elif filename.endswith("jsonl"):
        trace = pl.read_ndjson(filename)
    else:
        assert False, "unexpected file extension"

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


    def process(vtable):
        n_flows = 0
        ts = []
        flows = []
        keys = vtable.keys()
        
        for row in trace.filter(trace["event"].is_in(keys)).iter_rows(named=True):
            ts.append(row['ts']-1)
            flows.append(n_flows)
            
            # we must be sure that the event is always there
            n_flows = vtable[row["event"]](n_flows)

            ts.append(row["ts"])
            flows.append(n_flows)

        return pl.DataFrame({"ts": ts, "flows": flows})


    upcalls = trace.filter(trace["event"] == "UPCALL")
    filtered = upcalls.filter(upcalls["comm"].is_in(("python3", "analyzer")))

    return (process(table_change), process(cmd_change), upcalls, filtered)

def parse_tags(filename: str) -> pl.DataFrame:
    return pl.read_ndjson(filename)

def parse_pcap(filename: str) -> pl.DataFrame:
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
    return pl.DataFrame([s.__dict__ for s in stats])

def parse_udp_rr(filename: str) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """
    return values:
        1. latencies
        2. packets with timeouts
    """

    df = pl.read_csv(filename, dtypes={"latency_ns": pl.UInt64})

    latencies_only = df.filter(pl.col("latency_ns") != 0xFFFF_FFFF_FFFF_FFFF)
    dropped_only = df.filter(pl.col("latency_ns") == 0xFFFF_FFFF_FFFF_FFFF)

    return latencies_only, dropped_only


def parse_icmp_rtt(filename: str) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """
    return values:
        1. latencies
        2. packets with timeouts
    """

    df = pl.read_csv(filename, dtypes={"latency_us": pl.UInt64})

    latencies_only = df.lazy().filter(pl.col("latency_us") != 0xFFFF_FFFF_FFFF_FFFF).with_columns((pl.col("latency_us") * 1_000).alias("latency_ns")).collect()
    dropped_only = df.filter(pl.col("latency_us") == 0xFFFF_FFFF_FFFF_FFFF)

    return latencies_only, dropped_only



def parse_dpctl_dump(filename: str) -> pl.DataFrame:
    return pl.read_csv(filename)


def parse_vswitchd(filename: str) -> pl.DataFrame:
    return pl.read_csv(filename)

def parse_usdt(filename: str) -> Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    df = pl.read_csv(filename, separator=";", dtypes={"ts": pl.Int64, "flow_limit": pl.Int64, "duration_ns": pl.Int64, "flows": pl.Int64, "tid": pl.Int64})
    flow_limits = df.lazy().filter(pl.col("probe") == "new_flow_limit").drop("probe").collect()
    barriers = df.lazy().filter(pl.col("probe") != "new_flow_limit").filter(pl.col("probe").str.starts_with("ovs_").is_not()).filter(pl.col("duration_ns") != pl.col("ts")).drop("flow_limit").drop("flows").with_columns((pl.col("duration_ns").cast(pl.Float64) / 1_000_000_000).alias("duration_sec")).collect()
    kernel = df.lazy().filter(pl.col("probe").str.starts_with("ovs_")).drop("flow_limit").drop("flows").with_columns((pl.col("duration_ns").cast(pl.Float64) / 1_000_000_000).alias("duration_sec")).collect()
    return flow_limits, barriers, kernel

def renumber(col: str, df: pl.DataFrame) -> pl.DataFrame:
    ids = df.lazy().select(col).unique().with_row_count(name=f"{col}_num")
    return df.lazy().join(ids, on=col, how="inner").collect()

def remove_offset_and_scale(col: str, scale: float|int, *dfs: pl.DataFrame) -> list[pl.DataFrame]:
    low = float('inf')
    for df in dfs:
        if len(df) > 0:
            low = min(low, df.get_column(col).head(1).item() ) #df[col].iloc[0]
    
    res = []
    for df in dfs:
        #df = df.assign(**{col: (df[col] - low) * scale})
        df = df.with_columns(((pl.col(col) - low) * scale))
        res.append(df)
    return res


def normalize_ts(*args: pl.DataFrame) -> list[pl.DataFrame]:
    return remove_offset_and_scale('ts', 0.000_000_001, *args)