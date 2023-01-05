use std::{
    io::Write,
    os::unix::prelude::AsRawFd,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    time::Duration,
};

use memfd::MemfdOptions;
use subprocess::unix::PopenExt;

pub fn run_scapy_script(script: &[u8]) -> anyhow::Result<()> {
    let mfd = MemfdOptions::default().create("scapy-script.py")?;
    mfd.as_file().write_all(script)?;
    let script_fd = mfd.as_file().as_raw_fd();

    let mut exec = subprocess::Exec::cmd("python")
        .arg(format!("/proc/{}/fd/{}", nix::unistd::getpid(), script_fd))
        .detached()
        .popen()?;

    let stop = Arc::new(AtomicBool::new(false));
    signal_hook::flag::register(signal_hook::consts::SIGINT, Arc::clone(&stop)).unwrap();
    while !stop.load(Ordering::Relaxed) {
        let res = exec.wait_timeout(Duration::from_millis(200));
        stop.store(
            stop.load(Ordering::Relaxed) || res.is_ok_and(|f| f.is_some()),
            Ordering::Relaxed,
        );
    }

    let status = if stop.load(Ordering::Relaxed) {
        _ = exec.send_signal(libc::SIGINT);
        exec.wait_timeout(Duration::from_millis(500))
            .transpose()
            .unwrap_or_else(|| {
                _ = exec.kill();
                exec.wait()
            })
            .expect("failed to stop the scapy process")
    } else {
        // must have already stopped
        exec.exit_status().unwrap()
    };

    if status.success() {
        Ok(())
    } else {
        Err(anyhow::format_err!(
            "scapy process exited with exit code {:?}",
            status
        ))
    }
}
