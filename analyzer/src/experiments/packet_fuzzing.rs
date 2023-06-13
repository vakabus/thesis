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

    // upload results
    handler.handle_result(Path::new(&dumpfile));
    handler.handle_result(Path::new(&tagfile));
}
