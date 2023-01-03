use std::{io::Write, os::unix::prelude::AsRawFd, time::Duration, sync::{atomic::{Ordering, AtomicBool}, Arc}};

use libc::SIGINT;
use memfd::MemfdOptions;
use signal_hook::iterator::Signals;
use subprocess::{unix::PopenExt, ExitStatus};


pub fn run_scapy_script(script: &[u8]) -> anyhow::Result<()> {
    let mfd = MemfdOptions::default().create("scapy-script.py")?;
    mfd.as_file().write_all(script)?;
    let script_fd = mfd.as_file().as_raw_fd();


    let mut exec = subprocess::Exec::cmd("python").arg(format!("/proc/{}/fd/{}", nix::unistd::getpid(), script_fd)).detached().popen()?;
    
    let stop = Arc::new(AtomicBool::new(false));
    signal_hook::flag::register(signal_hook::consts::SIGINT, Arc::clone(&stop)).unwrap();
    while !stop.load(Ordering::Relaxed) {
        let res = exec.wait_timeout(Duration::from_millis(200));
        stop.store({
            let ref this = res;
            let f = |o: &Option<ExitStatus>| o.is_some();
            matches!(this, Ok(x) if f(x))
        }, Ordering::Relaxed);
    }

    let status = if stop.load(Ordering::Relaxed) {
        _ = exec.send_signal(libc::SIGINT);
        exec.wait_timeout(Duration::from_millis(500)).transpose().unwrap_or_else(|| {
            _ = exec.kill();
            exec.wait()
        }).expect("failed to stop the scapy process")
    } else {
        // must have already stopped
        exec.exit_status().unwrap()
    };

    if status.success() {
        Ok(())
    } else {
        Err(anyhow::format_err!("scapy process exited with exit code {:?}", status))
    }
}