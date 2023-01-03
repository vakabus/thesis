//! In this experiment
//!
use clap::Parser;

use std::{
    net::Ipv4Addr,
    str::FromStr,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread::sleep,
    time::Duration,
};

use crate::utils::blast::blast_udp_ipv4;

#[derive(Parser, Debug)]
pub struct BlastArgs {
    /// Number of IPs to send packets to during the blast
    #[arg(long, default_value_t = 1000)]
    blast_size: u32,

    /// IP address that starts the range of IPs being blasted by UDP packets
    #[arg(long, default_value_t = String::from("198.18.0.1"))]
    target_ip: String,

    /// send only one packet to each IP and then exit
    #[arg(short, long)]
    once: bool,
}

pub fn run(args: BlastArgs) {
    if args.once {
        blast_udp_ipv4(
            Ipv4Addr::from_str(&args.target_ip).expect("invalid ipv4"),
            args.blast_size,
        );
        info!("packets sent");
    } else {
        let period = Duration::from_millis(100);
        info!(
            "Sending UDP packets roughly every {:?}, interrupt with SIGINT to stop",
            period
        );

        let stop = Arc::new(AtomicBool::new(false));
        signal_hook::flag::register(signal_hook::consts::SIGINT, Arc::clone(&stop)).unwrap();
        while !stop.load(Ordering::Relaxed) {
            // send round of packets
            blast_udp_ipv4(
                Ipv4Addr::from_str(&args.target_ip).expect("invalid ipv4"),
                args.blast_size,
            );

            // wait a bit
            sleep(period);
        }

        info!("terminating...");
    }
}
