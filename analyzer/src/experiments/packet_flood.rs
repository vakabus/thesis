use std::{thread::sleep, time::Duration};

use anyhow::bail;
use clap::{ArgGroup, Parser};

use crate::utils::{clock_ns, raw_socket::RawSocket};

#[derive(Parser, Debug)]
#[clap(group(
    ArgGroup::new("number of packets")
        .required(true)
        .args(&["count", "interval_ns", "freq"]),
))]
pub struct PacketFloodArgs {
    /// How many flows to keep in the table.
    #[arg(long)]
    count: Option<u64>,

    /// How many times per second should we send packets
    #[arg(long)]
    freq: Option<u64>,

    /// a packet should be send every number of ns
    #[arg(long)]
    interval_ns: Option<u64>,

    /// For how long is a rule expected to stay in the table before being evicted.
    #[arg(long, default_value_t = 10_000_000_000)]
    eviction_ns: u64,
}

pub fn run(args: PacketFloodArgs) -> anyhow::Result<()> {
    let interval_ns: u64 = if let Some(cnt) = args.count {
        info!(
            "Targeting flow table with {} flow rules, assuming {:?} rule timeout.",
            cnt,
            Duration::from_nanos(args.eviction_ns)
        );
        args.eviction_ns / cnt
    } else if let Some(int) = args.interval_ns {
        info!(
            "Sending a unique packet every {:?}",
            Duration::from_nanos(int)
        );
        int
    } else if let Some(freq) = args.freq {
        info!(
            "Sending {} unique packets per second (uniformly spaced)",
            freq
        );
        1_000_000_000 / freq
    } else {
        bail!("unexpected combination of arguments");
    };

    let mut sent = 0;
    let start_time = clock_ns()?;
    let mut raw_socket = RawSocket::new();
    const SLEEP_THRESHOLD: Duration = Duration::from_micros(60);

    info!(
        "  => new rule every {:?} => expected {} rules in the flow table after {:?}",
        Duration::from_nanos(interval_ns),
        args.eviction_ns / interval_ns,
        Duration::from_nanos(args.eviction_ns)
    );
    info!("Flooding, stop with Ctrl+C");

    loop {
        // send as many packets as should have been sent by now
        let mut now = clock_ns()?;
        while sent * interval_ns + start_time < now {
            raw_socket.send_ethernet_pkt_from_unique_mac()?;
            sent += 1;
            let new_now = clock_ns()?;
            now = new_now;
        }

        let dur = Duration::from_nanos((sent * interval_ns + start_time) - now);
        if dur > SLEEP_THRESHOLD {
            sleep(dur);
        } else {
            // busy wait
        }
    }
}
