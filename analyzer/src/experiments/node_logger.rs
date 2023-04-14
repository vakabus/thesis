use std::{path::Path, time::Duration};

use clap::Parser;

use crate::utils::{
    dump_file, external_prog::run_external_program_async, ovs::OvsDpctlCollector,
    results_uploader::ResultHandler, vswitchd_monitor::SystemStatCollector, wait_for_signal,
};

#[derive(Parser, Debug)]
pub struct LogNodeArgs {
    /// trace only kernel flow table and upcalls, not anything additional
    #[arg(long, action)]
    only_upcalls: bool,
}

pub fn run(args: LogNodeArgs, handler: Box<impl ResultHandler + ?Sized>) -> anyhow::Result<()> {
    // prepare output file
    let filename_dumps = dump_file("log_ovs_dpctl_show", "csv");
    let filename_trace = dump_file("kernel_flow_table_trace", "csv");
    let filename_log = dump_file("trace_log", "jsonl");
    let filename_system = dump_file("vswitchd", "csv");

    /* start kernel tracing logging */
    let tracer_args = if args.only_upcalls {
        vec![
            "-w",
            &filename_trace,
            "-l",
            &filename_log,
            "--signal-ready",
            "--no-cmd",
        ]
    } else {
        vec!["-w", &filename_trace, "-l", &filename_log, "--signal-ready"]
    };
    let kernel_tracer = run_external_program_async(include_bytes!("log_flow_ops.py"), &tracer_args)
        .expect("failed to start kernel tracing");
    wait_for_signal(signal_hook::consts::SIGUSR1)?;

    /* system stat collector */
    let system_stats =
        SystemStatCollector::create(filename_system.clone(), Duration::from_millis(100));

    /* ovs-dpctl stats */
    let ovs_dpctl_stats =
        OvsDpctlCollector::create(filename_dumps.clone(), Duration::from_millis(100));

    /* wait for SIGINT to stop */
    info!("Collecting data. Press Ctrl+C or send SIGINT to stop.");
    wait_for_signal(signal_hook::consts::SIGINT).expect("waiting for signal failed");

    /* stop collectors */
    debug!("stopping kernel tracer");
    kernel_tracer.stop().expect("failed to stop kernel tracer");
    debug!("stopping system stat collector");
    system_stats.stop().expect("system stat collector failed");
    debug!("stopping dpctl collector");
    ovs_dpctl_stats
        .stop()
        .expect("ovs dpctl stat collector failed");
    debug!("data flushed");

    /* process results */
    handler.handle_result(Path::new(&filename_system));
    handler.handle_result(Path::new(&filename_dumps));
    handler.handle_result(Path::new(&filename_trace));
    handler.handle_result(Path::new(&filename_log));

    Ok(())
}
