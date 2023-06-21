#![feature(is_some_and)]
#![feature(result_option_inspect)]
#![feature(bigint_helper_methods)]

#[macro_use]
extern crate log;

use clap::Parser;
use log::Level;
use utils::results_uploader::{ResultHandler, ResultIgnorer, ResultsUploader};

mod experiments;
mod utils;

#[derive(Parser)]
#[command(author, version, about, long_about = None)]
struct Args {
    #[clap(long)]
    push_results_url: Option<String>,

    #[command(subcommand)]
    experiment: Experiments,
}

#[derive(clap::Subcommand, Debug)]
enum Experiments {
    /// Randomized measurement of flow eviction timeout
    ///
    /// Send ICMP ping packets in random intervals
    RandomizedEvictionTimeout(
        experiments::randomized_eviction_timeout::RandomizedEvictionTimeoutArgs,
    ),

    /// Collect statistics about OVS on a cluster node
    ///
    /// A general data collection tool used for monitoring OVS in high-resolution.
    /// Monitors upcalls, load averages, memory usage. Can also run a profiler. And more...
    NodeLogger(experiments::node_logger::LogNodeArgs),

    /// Packet fuzzing tool
    ///
    /// Generates packets according to the sw_flow_key struct in the openvswitch kernel module.
    /// 1000 at a time, then waits 11 seconds (the default timeout is 10 seconds)
    PacketFuzz(experiments::packet_fuzzing::PacketFuzzingArgs),

    /// Debugging tool for testing eBPF tracing
    ///
    /// A tool for testing a eBPF tracing, which is normally invoked
    /// as a part of the node-logger subcommand.
    LogFlowOps(experiments::log_flow_ops::LogFlowOpArgs),

    /// Install dependencies on the distro
    InstallDependencies(experiments::install_dependencies::InstallDepsArgs),

    /// Fill flow table with given number of rules
    ///
    /// Generate small packets with varying MAC addresses and send them
    /// to the default network interface. Sends packets in highly regular intervals.
    PacketFlood(experiments::packet_flood::PacketFloodArgs),

    /// Ethernet echo server
    ///
    /// A tool operating using a raw socket, reflecting the received packets back
    /// to their sender. It flips the Ethernet and IP source and destination headers.
    /// Automatically generated ICMP connection-refused packets are blocked using iptables.
    Reflector(experiments::pkt_reflector::ReflectorArgs),

    /// Latency measurement tool intended to be run in a pod on a stressed host
    ///
    /// Measures latency using ICMP and UDP. The UDP packets target the reflector
    /// service in the cluster (analyzer reflector), the ICMP packets target kb1 (192.168.1.221)
    Victim(experiments::victim::VictimArgs),

    /// Reload ovn-kubernetes on cluster node
    ///
    /// A simple script that helps with debugging OVS. USDT tracing
    /// is in some conditions buggy and restarting the container with
    /// ovs-vswitchd seems to help.
    ReloadOvn(experiments::reload_ovn::ReloadOvnArgs),
}

fn main() -> anyhow::Result<()> {
    // init logging
    simple_logger::init_with_level(Level::Debug).unwrap();

    // parse command line arguments
    let args = Args::parse();

    // results handler
    let handler: Box<dyn ResultHandler> = if args.push_results_url.is_some() {
        Box::new(ResultsUploader::new(args.push_results_url.unwrap()))
    } else {
        Box::new(ResultIgnorer::new())
    };

    match args.experiment {
        Experiments::RandomizedEvictionTimeout(ev) => {
            experiments::randomized_eviction_timeout::run(ev)
        }
        Experiments::NodeLogger(ev) => experiments::node_logger::run(ev, handler)?,
        Experiments::PacketFuzz(ev) => experiments::packet_fuzzing::run_experiment(ev, handler),
        Experiments::LogFlowOps(ev) => experiments::log_flow_ops::run_experiment(ev, handler),
        Experiments::InstallDependencies(ev) => {
            experiments::install_dependencies::run_experiment(ev)
        }
        Experiments::PacketFlood(ev) => experiments::packet_flood::run(ev)?,
        Experiments::Reflector(ev) => experiments::pkt_reflector::run(ev)?,
        Experiments::Victim(ev) => experiments::victim::run(ev, handler)?,
        Experiments::ReloadOvn(ev) => experiments::reload_ovn::run_experiment(ev),
    };

    Ok(())
}
