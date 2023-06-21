use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread::sleep,
    time::Duration,
};

use anyhow::bail;
use clap::{ArgGroup, Parser};

use crate::utils::{
    clock_ns,
    raw_socket::{IOUringRawSocket, RawSocket},
};

#[derive(Parser, Debug)]
#[clap(group(
    ArgGroup::new("number of packets")
        .required(true)
        .args(&["count", "interval_ns", "freq", "nolimit"]),
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

    /// how long to run for in seconds
    #[arg(long)]
    runtime_sec: Option<u64>,

    /// send packets as fast as possible, equivalent to --interval-ns 1
    #[arg(long)]
    nolimit: bool,
}

pub fn run(args: PacketFloodArgs) -> anyhow::Result<()> {
    let interval_ns = calculate_sending_interval_ns(&args)?;
    let mut sent = 0;
    let mut raw_socket = RawSocket::new();
    let ior = IOUringRawSocket::new()?;
    info!(
        "  => new rule every {:?} => expected {} rules in the flow table after {:?}",
        Duration::from_nanos(interval_ns),
        args.eviction_ns / interval_ns,
        Duration::from_nanos(args.eviction_ns)
    );
    info!("Flooding, stop with Ctrl+C");

    // when we are just about ready to start, initialize key timestamps
    let start_time = clock_ns()?;
    let end_time = if let Some(dur) = args.runtime_sec {
        start_time + dur * 1_000_000_000
    } else {
        u64::MAX
    };
    let mut stat_count: u64 = 1;

    let stop = Arc::new(AtomicBool::new(false));
    signal_hook::flag::register(signal_hook::consts::SIGINT, Arc::clone(&stop)).unwrap();
    while !stop.load(Ordering::Relaxed) {
        // send as many packets as should have been sent by now
        let now = clock_ns()?;

        /*
        // send packets using a normal socket
        let cnt = u64::min((now - start_time) / interval_ns - sent, 10_000);
        raw_socket.unique_mac_pkts_rapid_fire(cnt)?;
        sent += cnt;
        */

        /* send the packets using IO uring */
        let cnt = u64::min((now - start_time) / interval_ns - sent, 20_000);
        ior.sent_eth_pkts(sent, cnt as usize)?;
        sent += cnt;

        // sleeping shorter time durations than about 60us does not make sense
        // https://stackoverflow.com/questions/4986818/how-to-sleep-for-a-few-microseconds/71757858#71757858
        const SLEEP_THRESHOLD: Duration = Duration::from_micros(60);
        if sent * interval_ns + start_time >= now {
            // check that we are ahead of schedule, otherwise no delay
            let dur = Duration::from_nanos((sent * interval_ns + start_time) - now);
            if dur > SLEEP_THRESHOLD {
                sleep(dur);
            } else {
                // busy wait
            }
        }

        let now = clock_ns()?;
        if (now - start_time) / 5_000_000_000 == stat_count {
            stat_count += 1;
            let freq = (sent as f64) / (((now - start_time) as f64) / 1_000_000_000f64);
            info!("Sent {} packets so far, average {} pkt/s", sent, freq);
        }

        // termination condition
        if now > end_time {
            break;
        }
    }

    info!("Sent {} packets", sent);

    Ok(())
}

fn calculate_sending_interval_ns(args: &PacketFloodArgs) -> anyhow::Result<u64> {
    if args.nolimit {
        info!("Blasting packets as fast as possible!");
        Ok(1)
    } else if let Some(cnt) = args.count {
        info!(
            "Targeting flow table with {} flow rules, assuming {:?} rule timeout.",
            cnt,
            Duration::from_nanos(args.eviction_ns)
        );
        Ok(args.eviction_ns / cnt)
    } else if let Some(int) = args.interval_ns {
        info!(
            "Sending a unique packet every {:?}",
            Duration::from_nanos(int)
        );
        Ok(int)
    } else if let Some(freq) = args.freq {
        info!(
            "Sending {} unique packets per second (uniformly spaced)",
            freq
        );
        Ok(1_000_000_000 / freq)
    } else {
        bail!("unexpected combination of arguments");
    }
}
