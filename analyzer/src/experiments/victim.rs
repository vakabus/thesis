use std::{path::Path, time::Duration};

use clap::Parser;

use crate::utils::{
    dump_file,
    results_uploader::ResultHandler, wait_for_signal, rr::UdpRRCollector, latency::PingCollector,
};

#[derive(Parser, Debug)]
pub struct VictimArgs {
    
}

pub fn run(args: VictimArgs, handler: Box<impl ResultHandler + ?Sized>) -> anyhow::Result<()> {
    // prepare output file
    let filename_udp_rr = dump_file("udp_rr", "csv");
    let filename_icmp_rtt = dump_file("icmp_rtt", "csv");

    /* network latencies */
    let udp_rr = UdpRRCollector::create(filename_udp_rr.clone(), Duration::from_millis(50));
    let icmp_rr = PingCollector::create(filename_icmp_rtt.clone(), Duration::from_millis(75));

    /* wait for SIGINT to stop */
    info!("Collecting data. Press Ctrl+C or send SIGINT to stop.");
    wait_for_signal(signal_hook::consts::SIGINT).expect("waiting for signal failed");

    /* stop collectors */
    debug!("Stopping UDP RR collector");
    udp_rr.stop().expect("UDP rr collector failed");
    debug!("stopping ICMP collector");
    icmp_rr.stop().expect("failed to stop ping collector");
    debug!("data flushed");

    /* process results */
    handler.handle_result(Path::new(&filename_udp_rr));
    handler.handle_result(Path::new(&filename_icmp_rtt));

    Ok(())
}