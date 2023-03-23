//! In this experiment
//!
use clap::Parser;
use csv::WriterBuilder;
use rand::Rng;
use std::{net::IpAddr, str::FromStr, thread::sleep, time::Duration};

use crate::utils::latency::ping_twice;

#[derive(Parser, Debug)]
pub struct RandomizedEvictionTimeoutArgs {
    /// Starting time delay between samples
    #[arg(long, default_value_t = 8000)]
    delay_min: u64,

    /// What is the largest time delay between samples we should measure
    #[arg(long, default_value_t = 12000)]
    delay_max: u64,

    #[arg(long, default_value_t = String::from("192.168.1.1"))]
    target_ip: String,
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
    output
        .write_record(["us_since_last_measurement", "us_latency1", "us_latency2"])
        .unwrap(); // header

    // warmup
    _ = ping_twice(addr);

    loop {
        cnt += 1;

        // sleep randomly
        let sleep_time =
            Duration::from_millis(rand::thread_rng().gen_range(args.delay_min..args.delay_max));
        sleep(sleep_time);

        // measure
        match ping_twice(addr) {
            Ok((d1, d2)) => {
                // write
                output
                    .write_record(&[
                        sleep_time.as_micros().to_string(),
                        d1.as_micros().to_string(),
                        d2.as_micros().to_string(),
                    ])
                    .unwrap();
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
