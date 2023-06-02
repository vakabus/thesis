use std::time::Duration;

use anyhow::{bail, Result};
use procfs::process::Process;
use serde::Serialize;

use super::{
    clock_ns,
    collector::{CSVCollector, Monitor},
};

pub struct VSwitchdMonitor {
    proc: Process,
}

#[derive(Debug, Serialize)]
pub struct Datapoint {
    ts: u64,
    vswitchd_utime_sec: f64,
    vswitchd_stime_sec: f64,
    vswitchd_rss_bytes: u64,
    vswitchd_threads: u32,
    vswitchd_vsize_bytes: u64,
}

fn get_vswitchd_proc() -> Result<Process> {
    for proc in procfs::process::all_processes()? {
        let proc = proc?;
        if let Ok(stat) = proc.stat() {
            if stat.comm == "ovs-vswitchd" {
                return Ok( proc );
            }
        }
    }
    bail!("no ovs-vswitchd found");
}

impl Monitor for VSwitchdMonitor {
    type Stats = Datapoint;

    fn new() -> Result<Self> {
        let proc = get_vswitchd_proc()?;
        Ok(VSwitchdMonitor { proc })
    }

    fn collect(&mut self) -> anyhow::Result<Datapoint> {
        if ! self.proc.is_alive() {
            self.proc = get_vswitchd_proc()?;
        }

        let stat = self.proc.stat()?;

        Ok(Datapoint {
            ts: clock_ns()?,
            vswitchd_stime_sec: (stat.stime as f64) / (procfs::ticks_per_second() as f64),
            vswitchd_utime_sec: (stat.utime as f64) / (procfs::ticks_per_second() as f64),
            vswitchd_rss_bytes: stat.rss_bytes(),
            vswitchd_threads: stat.num_threads as u32,
            vswitchd_vsize_bytes: stat.vsize,
        })
    }
}

pub type SystemStatCollector = CSVCollector<VSwitchdMonitor>;
