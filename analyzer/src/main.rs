#![feature(is_some_and)]

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

    /// rapidly send UDP packets to IPv4 in a defined sequence
    Blast(experiments::blast::BlastArgs),

    /// collect ovs-dpctl show stats
    LogFlowStats(experiments::log_ovs_dpctl_stats::LogArgs),

    /// TUI with real-time system information
    Monitor(experiments::monitor::MonitorArgs),

    /// run packet fuzzing
    PacketFuzz(experiments::packet_fuzzing::PacketFuzzingArgs),

    /// test EBPF flow monitoring
    LogFlowOps(experiments::log_flow_ops::LogFlowOpArgs),

    /// Install dependencies on the distro
    InstallDependencies(experiments::install_dependencies::InstallDepsArgs),
}

fn main() {
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
        Experiments::Blast(ev) => experiments::blast::run(ev),
        Experiments::LogFlowStats(ev) => experiments::log_ovs_dpctl_stats::run(ev, handler),
        Experiments::Monitor(ev) => experiments::monitor::run(ev),
        Experiments::PacketFuzz(ev) => experiments::packet_fuzzing::run_experiment(ev, handler),
        Experiments::LogFlowOps(ev) => experiments::log_flow_ops::run_experiment(ev, handler),
        Experiments::InstallDependencies(ev) => {
            experiments::install_dependencies::run_experiment(ev)
        }
    }
}
