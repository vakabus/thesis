#[macro_use]
extern crate log;

use std::sync::mpsc::Receiver;
use std::thread::sleep;
use std::time::Duration;

use clap::Parser;

use fastping_rs::PingResult::{Idle, Receive, self};
use fastping_rs::Pinger;
use log::Level;

fn create_pinger() -> (Pinger, Receiver<PingResult>) {
    match Pinger::new(None, Some(56)) {
        Ok((pinger, results)) => (pinger, results),
        Err(e) => panic!("Error creating pinger: {}", e),
    }
}

fn one_measurement(ip: &str, pinger: &Pinger, results: &Receiver<PingResult>) -> Duration {
    pinger.add_ipaddr(ip);
    pinger.ping_once();
    match results.recv() {
        Ok(result) => match result {
            Idle { addr } => {
                error!("No reply for ICMP ping from {}", addr);
                panic!();
            }
            Receive { addr, rtt } => {
                debug!("ping {} --> {:?}.", addr, rtt);
                pinger.remove_ipaddr(ip);
                rtt
            }
        },
        Err(_) => panic!("Worker threads disconnected before the solution was found!"),
    }
}

fn abs_diff(d1: Duration, d2: Duration) -> Duration {
    if d1 > d2 {
        d1 - d2
    } else {
        d2 - d1
    }
}


fn ping_difference(ip: &str) -> Duration {
    let (pinger, results) = create_pinger();

    // the first one is special
    let first = one_measurement(ip, &pinger, &results);

    // then take average of three
    let second = one_measurement(ip, &pinger, &results);

    // and return the difference
    abs_diff(first, second)
}


fn measurement(ip: &str, cnt: usize, time_in_between: Duration) -> Vec<Duration> {
    let mut results = Vec::with_capacity(cnt);

    _ = ping_difference(ip);  // warm up (this will insert a flow into the kernel)
    for _ in 0..cnt {
        sleep(time_in_between);
        results.push(ping_difference(ip));
    }

    results
}



/// Simple program to greet a person
#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
   /// Time difference between measurements
   #[arg(long, default_value_t = 15_000)]
   gap: u64,

   /// Number of samples per measurement
   #[arg(long, default_value_t = 5)]
   samples: u32,

   /// Starting time delay between samples
   #[arg(long, default_value_t = 4000)]
   delay_first_ms: u64,

   /// By how much should we increase time delay between samples in every measurement
   #[arg(long, default_value_t = 500)]
   delay_step_ms: u64,

   /// What is the largest time delay between samples we should measure
   #[arg(long, default_value_t = 12000)]
   delay_stop_ms: u64,
}

fn main() {
    // init logging
    simple_logger::init_with_level(Level::Info).unwrap();

    // parse command line arguments
    let args = Args::parse();

    let mut time_in_between = Duration::from_millis(args.delay_first_ms);
    let step = Duration::from_millis(args.delay_step_ms);

    loop {
        let mut measurements = measurement("192.168.1.1", args.samples as usize, time_in_between);
        measurements.sort();
        // ignore outliars
        let avg: Duration = measurements.iter().skip(1).take(measurements.len() - 2).sum::<Duration>() / args.samples;
        info!("{}ms -> difference {}us {:?}", time_in_between.as_millis(), avg.as_micros(), measurements);

        debug!("Waiting before a new measurement");
        sleep(Duration::from_millis(args.gap));

        if time_in_between > Duration::from_secs(15) {
            break;
        } else {
            time_in_between += step;
        }
    }    
}