use std::fs;

use anyhow::Result;
use serde::Serialize;

use super::{
    clock_ns,
    collector::{CSVCollector, Monitor},
};

pub struct LoadavgMonitor {}

#[derive(Debug, Serialize)]
pub struct Datapoint {
    ts: u64,
    loadavg1: f64,
    loadavg5: f64,
    loadavg15: f64,
    proc_running: u32,
    proc_all: u32,
}

impl Monitor for LoadavgMonitor {
    type Stats = Datapoint;

    fn new() -> Result<Self> {
        Ok(LoadavgMonitor {})
    }

    fn collect(&mut self) -> anyhow::Result<Datapoint> {
        let contents = fs::read_to_string("/proc/loadavg")?;

        let mut it = contents.split(' ');
        let loadavg1 = it.next().unwrap();
        let loadavg5 = it.next().unwrap();
        let loadavg15 = it.next().unwrap();
        let procs = it.next().unwrap();

        let mut it = procs.split('/');
        let running = it.next().unwrap();
        let all = it.next().unwrap();

        Ok(Datapoint {
            ts: clock_ns()?,
            loadavg1: loadavg1.parse()?,
            loadavg5: loadavg5.parse()?,
            loadavg15: loadavg15.parse()?,
            proc_running: running.parse()?,
            proc_all: all.parse()?,
        })
    }
}

pub type LoadavgCollector = CSVCollector<LoadavgMonitor>;
