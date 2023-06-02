use anyhow::{anyhow, Result};
use csv::{WriterBuilder, Writer};

use serde::Serialize;
use std::{
    marker::PhantomData,
    path::Path,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread::{sleep, JoinHandle},
    time::Duration, fs::File,
};

use super::{block_signals};

pub trait MultiMonitor {
    type Stats: Serialize + Sized;

    fn new() -> Result<Self>
    where
        Self: Sized;

    fn collect_multiple(&mut self) -> Result<Vec<Self::Stats>>;
}

pub trait Monitor {  
    type Stats: Serialize + Sized;

    fn new() -> Result<Self>
    where
        Self: Sized;

    fn collect(&mut self) -> Result<Self::Stats>;
}

impl<T: Monitor> MultiMonitor for T {
    type Stats = T::Stats;
    
    fn collect_multiple(&mut self) -> Result<Vec<Self::Stats>> {
        self.collect().map(|r| vec![r])
    }


    fn new() -> Result<Self>
    where Self: Sized {
        T::new()
    }
}


pub struct CSVCollector<M: MultiMonitor> {
    stop_flag: Arc<AtomicBool>,
    thread_handle: JoinHandle<Result<()>>,
    collect_func_type: PhantomData<M>,
}

impl<M: MultiMonitor> CSVCollector<M> {
    pub fn create(filename: String, interval: Duration) -> Self {
        let stop_flag = Arc::new(AtomicBool::new(false));
        let stop_flag2 = stop_flag.clone();

        let handle = std::thread::Builder::new()
            .name(filename.clone())
            .spawn(move || CSVCollector::<M>::run_collector(stop_flag, filename, interval))
            .expect("failed to spawn a new thread");

        CSVCollector {
            thread_handle: handle,
            stop_flag: stop_flag2,
            collect_func_type: PhantomData::default(),
        }
    }

    fn collect_and_write(monitor: &mut M, output: &mut Writer<File>) -> Result<()> {
        // collect and write data
        let stats = monitor.collect_multiple()?;
        for st in stats {
            output.serialize(st)?;
        }
        Ok(())
    }

    fn run_collector(
        stop_flag: Arc<AtomicBool>,
        filename: String,
        interval: Duration,
    ) -> anyhow::Result<()> {
        block_signals();

        let mut output = WriterBuilder::new()
            .from_path(Path::new(&filename))
            .unwrap();

        let mut monitor = M::new().unwrap();

        while !stop_flag.load(Ordering::Relaxed) {
            _ = Self::collect_and_write(&mut monitor, &mut output); // ignore errors

            // wait
            sleep(interval);
        }

        output.flush()?;
        Ok(())
    }

    pub fn stop(self) -> Result<()> {
        self.stop_flag.store(true, Ordering::Relaxed);
        let res = self.thread_handle.join();
        match res {
            Err(_) => Err(anyhow!("the stat collector thread panicked")),
            Ok(o) => o,
        }
    }
}
