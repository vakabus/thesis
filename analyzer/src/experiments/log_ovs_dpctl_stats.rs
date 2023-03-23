use std::{
    net::{IpAddr, UdpSocket},
    path::Path,
    str::FromStr,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread::{self, sleep},
    time::{Duration, Instant},
};

use clap::Parser;
use csv::WriterBuilder;

use crate::utils::{
    dump_file, external_prog::run_external_program_async, ovs::get_ovs_dpctl_show,
    results_uploader::ResultHandler,
};

#[derive(Parser, Debug)]
pub struct LogArgs {
    // an IP where the collected data will be sent in UDP packets as json
    #[arg(short, long, default_value_t = String::from("127.0.0.1"))]
    log_ip: String,
}

pub fn run(args: LogArgs, handler: Box<impl ResultHandler + ?Sized>) {
    // prepare output file
    let filename_dumps = dump_file("log_ovs_dpctl_show", "csv");
    let filename_trace = dump_file("kernel_flow_table_trace", "jsonl");
    let filename_log = dump_file("trace_log", "jsonl");

    info!(
        "results will be written to '{}' and '{}'",
        filename_dumps, filename_trace
    );
    let mut output = WriterBuilder::new()
        .from_path(Path::new(&filename_dumps))
        .unwrap();

    let start = Instant::now();
    let ms10 = Duration::from_millis(10);

    /* initialize UDP socket for network logging */
    let udp_socket = UdpSocket::bind("0.0.0.0:0").expect("failed to bind a UDP socket");
    udp_socket
        .connect((IpAddr::from_str(&args.log_ip).unwrap(), 9876))
        .expect("failed to connect the UDP socket to target IP");

    /* start kernel tracing logging */
    let kernel_tracer =
        run_external_program_async(include_bytes!("log_flow_ops.py"), &["-w", &filename_trace, "-l", &filename_log])
            .expect("failed to start kernel tracing");
    sleep(Duration::from_secs(5)); /* give it a change to start tracing */

    /* start dumping loop */
    let stop = Arc::new(AtomicBool::new(false));
    signal_hook::flag::register(signal_hook::consts::SIGINT, Arc::clone(&stop)).unwrap();
    while !stop.load(Ordering::Relaxed) {
        let stats = get_ovs_dpctl_show(start);
        match stats {
            Ok(stats) => {
                output
                    .serialize(&stats)
                    .expect("failed to serializace data to CSV");
                _ = udp_socket.send(
                    serde_json::to_string(&stats)
                        .expect("serialization failed")
                        .as_bytes(),
                ); // don't care about success
            }
            Err(err) => warn!("error collecting data: {:?}", err),
        };

        sleep(ms10);
    }

    kernel_tracer.wait().expect("failed to stop kernel tracer");
    output.flush().expect("failed to flush data");
    info!("data flushed");

    /* process results */
    handler.handle_result(Path::new(&filename_dumps));
    handler.handle_result(Path::new(&filename_trace));
    handler.handle_result(Path::new(&filename_log));
}
