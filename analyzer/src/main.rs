#![feature(is_some_and)]
#![feature(result_option_inspect)]

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
    /// measure flow eviction timeout
    EvictionTimeout(experiments::eviction_timeout::EvictionTimeoutArgs),

    /// randomized measurement of flow eviction timeout
    RandomizedEvictionTimeout(
        experiments::randomized_eviction_timeout::RandomizedEvictionTimeoutArgs,
    ),

    /// collect ovs-dpctl show stats
    NodeLogger(experiments::node_logger::LogNodeArgs),

    /// run packet fuzzing
    PacketFuzz(experiments::packet_fuzzing::PacketFuzzingArgs),

    /// test EBPF flow monitoring
    LogFlowOps(experiments::log_flow_ops::LogFlowOpArgs),

    /// Install dependencies on the distro
    InstallDependencies(experiments::install_dependencies::InstallDepsArgs),

    /// Fill flow table with given number of rules
    PacketFlood(experiments::packet_flood::PacketFloodArgs),

    /// Ethernet echo server
    Reflector(experiments::pkt_reflector::ReflectorArgs),

    /// Innocent victim
    Victim(experiments::victim::VictimArgs),

    /// Reload ovn-kubernetes on node
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
        Experiments::EvictionTimeout(ev) => experiments::eviction_timeout::run_experiment(ev),
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
