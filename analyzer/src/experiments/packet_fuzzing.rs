//! In this experiment
//!
use std::{
    net::UdpSocket,
    path::Path,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread,
    time::Duration,
};

use clap::Parser;
use local_ip_address::local_ip;

use crate::utils::{
    dump_file, external_prog::run_external_program_script, results_uploader::ResultHandler,
    tcpdump::TcpDump,
};

#[derive(Parser, Debug)]
pub struct PacketFuzzingArgs {}

pub fn run_experiment(_args: PacketFuzzingArgs, handler: Box<impl ResultHandler + ?Sized>) {
    let socket =
        UdpSocket::bind("0.0.0.0:9876").expect("failed to bind socket for receiving stats");
    socket.set_read_timeout(None).unwrap();
    info!(
        "please run `analyzer log-flow-stats --log-ip {}` on Kubernetes node where the pod runs",
        local_ip().unwrap()
    );
    info!("waiting for statistics packet");

    // wait until we receive data
    let mut buf = vec![0u8; 8];
    let (_size, addr) = socket.recv_from(&mut buf).unwrap();
    info!(
        "got a logging packet from {:?}, starting scapy script",
        addr
    );

    let stop_thread = Arc::new(AtomicBool::new(false));
    let stop_thread_thread = stop_thread.clone();
    let packet_collector_thread = thread::spawn(move || {
        socket
            .set_read_timeout(Some(Duration::from_millis(500)))
            .unwrap();
        while !stop_thread_thread.load(Ordering::Relaxed) {
            // we don't care about the received data, it is captured by tcpdump
            // but we have to get it out of the kernel
            let _a = socket.recv(&mut buf);
        }
    });

    // run the actual experiment
    let dumpfile = dump_file("packet_capture", "pcap");
    let tagfile = dump_file("tags", "jsonl");

    {
        let _tcpdump = TcpDump::start_capture(&dumpfile).expect("tcpdump failed");
        let result = run_external_program_script(include_bytes!("packet_fuzzing.py"), &[&tagfile]);
        if let Err(e) = result {
            warn!("scapy execution error: {}", e);
        }
    }

    // stop the thread
    info!("script finished, cleaning up");
    stop_thread.store(true, Ordering::Relaxed);
    _ = packet_collector_thread.join();

    // upload results
    handler.handle_result(Path::new(&dumpfile));
    handler.handle_result(Path::new(&tagfile));
}