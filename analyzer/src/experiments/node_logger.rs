use std::{path::Path, time::Duration};

use clap::Parser;

use crate::utils::{
    dump_file, external_prog::{run_external_program_async}, ovs::OvsDpctlCollector,
    results_uploader::ResultHandler, vswitchd_monitor::SystemStatCollector, wait_for_signal, wait_for_signal_or_timeout, loadavg::LoadavgCollector,
};

#[derive(Parser, Debug)]
pub struct LogNodeArgs {
    /// trace only kernel flow table and upcalls, not anything additional
    #[arg(long, action)]
    only_upcalls: bool,

    /// how long to run for
    #[arg(long)]
    runtime_sec: Option<u64>,

    /// record perf
    #[arg(long, action)]
    perf: bool,

    /// record offcputime
    #[arg(long, action)]
    offcputime: bool,
}

pub fn run(args: LogNodeArgs, handler: Box<impl ResultHandler + ?Sized>) -> anyhow::Result<()> {
    // prepare output file
    let filename_dumps = dump_file("log_ovs_dpctl_show", "csv");
    let filename_trace = dump_file("kernel_flow_table_trace", "csv");
    let filename_log = dump_file("trace_log", "jsonl");
    let filename_system = dump_file("vswitchd", "csv");
    let filename_perf = dump_file("ovs-vswitchd", "perf.tar.bz2");
    let filename_usdt = dump_file("ovs-vswitchd-usdt", "csv");
    let filename_offcputime = dump_file("offcputime", "log");
    let filename_loadavg = dump_file("loadavg", "csv");

    /* start kernel tracing logging */
    let tracer_args = if args.only_upcalls {
        vec![
            "-w",
            &filename_trace,
            "-l",
            &filename_log,
            "--signal-ready",
            "--no-cmd",
            "--buffer-page-count",
            "10240",
        ]
    } else {
        vec!["-w", &filename_trace, "-l", &filename_log, "--signal-ready"]
    };
    let kernel_tracer = run_external_program_async(include_bytes!("log_flow_ops.py"), &tracer_args)
        .expect("failed to start kernel tracing");
    wait_for_signal(signal_hook::consts::SIGUSR1)?;

    /* perf */
    let mut perf = None;
    if args.perf {
        perf = Some(run_external_program_async(include_bytes!("node_logger_perf.sh"), &[&filename_perf])?);
    }

    /* offcputime */
    let mut offcputime = None;
    if args.offcputime {
        offcputime = Some(run_external_program_async(include_bytes!("node_logger_offcputime.sh"), &[&filename_offcputime])?);
    }

    let usdt = run_external_program_async(include_bytes!("node_logger_usdt.sh"), &[&filename_usdt])?;

    /* system stat collector */
    let system_stats =
        SystemStatCollector::create(filename_system.clone(), Duration::from_millis(100));

    let loadavg = LoadavgCollector::create(filename_loadavg.clone(), Duration::from_millis(100));

    /* ovs-dpctl stats */
    let ovs_dpctl_stats =
        OvsDpctlCollector::create(filename_dumps.clone(), Duration::from_millis(100));

    if let Some(runtime) = args.runtime_sec {
        /* run for the given time or until Ctrl+C */
        info!("Collecting data for {} sec. Press Ctrl+C / SIGINT to interrupt.", runtime);
        wait_for_signal_or_timeout(signal_hook::consts::SIGINT, Duration::from_secs(runtime)).expect("waiting for signal failed");
    } else {
        /* wait for SIGINT to stop */
        info!("Collecting data. Press Ctrl+C or send SIGINT to stop.");
        wait_for_signal(signal_hook::consts::SIGINT).expect("waiting for signal failed");
    }

    /* stop collectors */
    info!("stopping ovs_dpctl_stats");
    _ = ovs_dpctl_stats.stop().inspect_err(|e| warn!("collector failed: {}", e));
    info!("stopping system stats");
    _ = system_stats.stop().inspect_err(|e| warn!("collector failed: {}", e));
    info!("stopping loadavg collector");
    _ = loadavg.stop().inspect_err(|e| warn!("loadavg collector failed: {}", e));
    info!("stopping kernel tracer");
    _ = kernel_tracer.stop().inspect_err(|e| warn!("collector failed: {}", e));
    info!("stopping usdt tracer");
    _ = usdt.stop().inspect_err(|e| warn!("usdt tracer failed: {}", e));
    info!("stopping perf");
    if let Some(perf) = perf { _ = perf.stop_with_timeout(Duration::from_secs(120)).inspect_err(|e| warn!("collector failed: {}", e)); }
    info!("stopping offcputime");
    if let Some(offcputime) = offcputime { _ = offcputime.stop().inspect_err(|e| warn!("offcputime stop error: {}", e))};
    debug!("data flushed");

    /* process results */
    handler.handle_result(Path::new(&filename_system));
    handler.handle_result(Path::new(&filename_dumps));
    handler.handle_result(Path::new(&filename_trace));
    handler.handle_result(Path::new(&filename_log));
    handler.handle_result(Path::new(&filename_perf));
    handler.handle_result(Path::new(&filename_usdt));
    handler.handle_result(Path::new(&filename_offcputime));
    handler.handle_result(Path::new(&filename_loadavg));

    Ok(())
}
