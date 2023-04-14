//! In this experiment
//!
use clap::Parser;
use csv::WriterBuilder;
use std::{net::IpAddr, str::FromStr, thread::sleep, time::Duration};

use crate::utils::latency::{ping, ping_twice};

#[derive(Parser, Debug)]
pub struct EvictionTimeoutArgs {
    /// Time difference between samples
    /// After this period, we assume the system is not influenced by previous measurement
    #[arg(long, default_value_t = 15_000)]
    gap: u64,

    /// Number of samples per measurement
    #[arg(long, default_value_t = 20)]
    samples: u32,

    /// Starting time delay between samples
    #[arg(long, default_value_t = 6000)]
    delay_first_ms: u64,

    /// By how much should we increase time delay between samples in every measurement
    #[arg(long, default_value_t = 500)]
    delay_step_ms: u64,

    /// What is the largest time delay between samples we should measure
    #[arg(long, default_value_t = 10000)]
    delay_stop_ms: u64,

    #[arg(long, default_value_t = String::from("192.168.1.1"))]
    target_ip: String,
}

fn one_latency_difference_measurement(
    ip: IpAddr,
    cnt: usize,
    time_in_between: Duration,
) -> Vec<(Duration, Duration)> {
    let mut results = Vec::with_capacity(cnt);

    _ = ping(ip); // warm up (this will insert a flow into the kernel)
    for _ in 0..cnt {
        sleep(time_in_between);
        results.push(ping_twice(ip).expect("ping failed"));
    }

    results
}

pub fn run_experiment(args: EvictionTimeoutArgs) {
    let mut time_in_between = Duration::from_millis(args.delay_first_ms);
    let step = Duration::from_millis(args.delay_step_ms);
    let addr = IpAddr::from_str(&args.target_ip).expect("invalid IP");

    // prepare output file
    let filename = format!("eviction_timeout_{}.csv", chrono::Local::now().to_rfc3339());
    info!("results will be written to {}", filename);
    let mut output = WriterBuilder::new().from_path(filename).unwrap();
    output
        .write_record(["us_between_measurements", "us_latency1", "us_latency2"])
        .unwrap(); // header

    loop {
        info!(
            "measuring latency difference of consecutive pings with delay {:?}",
            time_in_between
        );
        let samples =
            one_latency_difference_measurement(addr, args.samples as usize, time_in_between);

        // save data
        for (d1, d2) in samples {
            output
                .write_record(&[
                    time_in_between.as_micros().to_string(),
                    d1.as_micros().to_string(),
                    d2.as_micros().to_string(),
                ])
                .unwrap();
        }
        output.flush().expect("failed to flush results to disk");

        // print fancy log message and wait for next
        info!("  [OK] done");
        info!("waiting before next measurement");
        sleep(Duration::from_millis(args.gap));

        if time_in_between >= Duration::from_millis(args.delay_stop_ms) {
            break;
        } else {
            time_in_between += step;
        }
    }
}
