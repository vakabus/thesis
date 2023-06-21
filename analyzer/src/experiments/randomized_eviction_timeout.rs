//! In this experiment
//!
use clap::Parser;
use csv::WriterBuilder;
use rand::Rng;
use std::{net::IpAddr, str::FromStr, thread::sleep, time::Duration};

use crate::utils::latency::{ping_multiple, ping_twice};

#[derive(Parser, Debug)]
pub struct RandomizedEvictionTimeoutArgs {
    /// starting time delay between samples
    #[arg(long, default_value_t = 8000)]
    delay_min: u64,

    /// what is the largest time delay between samples we should measure
    #[arg(long, default_value_t = 12000)]
    delay_max: u64,

    /// where do we send the ICMP packets
    #[arg(long, default_value_t = String::from("192.168.1.221"))]
    target_ip: String,

    /// number of consecutive pings
    #[arg(long, default_value_t = 2)]
    count: usize,
}

pub fn run(args: RandomizedEvictionTimeoutArgs) {
    let addr = IpAddr::from_str(&args.target_ip).expect("invalid IP");
    let mut cnt: usize = 0;

    // prepare output file
    let filename = format!(
        "randomized_eviction_timeout_{}.csv",
        chrono::Local::now().to_rfc3339()
    );
    info!("results will be written to {}", filename);
    let mut output = WriterBuilder::new().from_path(filename).unwrap();

    let mut header = vec!["us_since_last_measurement".to_owned()];
    for i in 0..args.count {
        header.push(format!("us_latency{}", i + 1));
    }
    output.write_record(header).unwrap(); // header

    // warmup
    _ = ping_twice(addr);

    loop {
        cnt += 1;

        // sleep randomly
        let sleep_time =
            Duration::from_millis(rand::thread_rng().gen_range(args.delay_min..args.delay_max));
        sleep(sleep_time);

        // measure
        match ping_multiple(args.count, addr) {
            Ok(durs) => {
                let mut record = vec![sleep_time.as_micros().to_string()];
                record.extend(durs.into_iter().map(|d| d.as_micros().to_string()));

                // write
                output.write_record(record).unwrap();
                output.flush().expect("failed to flush results to disk");

                // print fancy log message and wait for next
                if cnt % 10 == 0 {
                    info!("{} samples collected", cnt);
                }
            }
            Err(e) => {
                warn!("ping failed: {}", e);

                // we don't know, what has happened and it could potentially poison our data for the next measurement
                // so we run a ping again just to make sure the flow rules are in the kernel
                _ = ping_twice(addr).expect("ping failed for the second time in a row");
            }
        }
    }
}
