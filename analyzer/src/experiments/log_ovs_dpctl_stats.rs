use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread::sleep,
    time::{Duration, Instant}, net::{UdpSocket, IpAddr}, str::FromStr,
};

use clap::Parser;
use csv::WriterBuilder;

use crate::utils::ovs::get_ovs_dpctl_show;

#[derive(Parser, Debug)]
pub struct LogArgs {
    // an IP where the collected data will be sent in UDP packets as json
    #[arg(short, long, default_value_t = String::from("127.0.0.1"))]
    log_ip: String,
}

pub fn run(args: LogArgs) {
    // prepare output file
    let filename = format!(
        "log_ovs_dpctl_show_{}.csv",
        chrono::Local::now().to_rfc3339()
    );
    info!("results will be written to {}", filename);
    let mut output = WriterBuilder::new().from_path(filename).unwrap();

    let start = Instant::now();
    let ms10 = Duration::from_millis(10);

    let udp_socket = UdpSocket::bind("0.0.0.0:0").expect("failed to bind the UDP socket");
    udp_socket.connect((IpAddr::from_str(&args.log_ip).unwrap(), 9876)).expect("failed to connect the UDP socket to target IP");

    let stop = Arc::new(AtomicBool::new(false));
    signal_hook::flag::register(signal_hook::consts::SIGINT, Arc::clone(&stop)).unwrap();
    while !stop.load(Ordering::Relaxed) {
        let stats = get_ovs_dpctl_show(start);
        match stats {
            Ok(stats) =>  {
                output
                    .serialize(&stats)
                    .expect("failed to serializace data to CSV");
                _ = udp_socket.send(serde_json::to_string(&stats).expect("serialization failed").as_bytes()); // don't care about success
            },
            Err(err) => warn!("error collecting data: {:?}", err),
        };

        sleep(ms10);
    }

    output.flush().expect("failed to flush data");
    info!("data flushed, bye bye");
}
