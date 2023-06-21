use std::{
    io::Write,
    os::unix::prelude::AsRawFd,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    time::Duration,
};

use memfd::{Memfd, MemfdOptions};
use subprocess::{unix::PopenExt, Popen};

pub struct ExternalProg {
    popen: Popen,
    _mfd: Option<Memfd>, // just to keep a reference to it the whole time the program is running
}

impl ExternalProg {
    pub fn wait(mut self) -> anyhow::Result<()> {
        let stop = Arc::new(AtomicBool::new(false));
        signal_hook::flag::register(signal_hook::consts::SIGINT, Arc::clone(&stop)).unwrap();
        while !stop.load(Ordering::Relaxed) {
            let res = self.popen.wait_timeout(Duration::from_millis(200));
            stop.store(
                stop.load(Ordering::Relaxed) || res.is_ok_and(|f| f.is_some()),
                Ordering::Relaxed,
            );
        }

        self.stop()
    }

    pub fn stop(self) -> anyhow::Result<()> {
        self.stop_with_timeout(Duration::from_millis(2000))
    }

    pub fn stop_with_timeout(mut self, timeout: Duration) -> anyhow::Result<()> {
        let status = if let Some(st) = self.popen.exit_status() {
            st
        } else {
            _ = self.popen.send_signal(libc::SIGINT);
            self.popen
                .wait_timeout(timeout)
                .transpose()
                .unwrap_or_else(|| {
                    _ = self.popen.kill();
                    self.popen.wait()
                })
                .expect("failed to stop the external process")
        };

        if status.success() {
            Ok(())
        } else {
            Err(anyhow::format_err!(
                "process exited with exit code {:?}",
                status
            ))
        }
    }
}

pub fn run_external_program_async(script: &[u8], args: &[&str]) -> anyhow::Result<ExternalProg> {
    let mfd = MemfdOptions::default().create("external-program")?;
    mfd.as_file().write_all(script)?;
    let script_fd = mfd.as_file().as_raw_fd();

    let exec = subprocess::Exec::cmd(format!("/proc/{}/fd/{}", nix::unistd::getpid(), script_fd))
        .args(args)
        .detached()
        .popen()?;

    Ok(ExternalProg {
        popen: exec,
        _mfd: Some(mfd),
    })
}

pub fn run_cmd_async(cmd: &[&str]) -> anyhow::Result<ExternalProg> {
    let exec = subprocess::Exec::cmd(cmd[0])
        .args(&cmd[1..])
        .detached()
        .popen()?;

    Ok(ExternalProg {
        popen: exec,
        _mfd: None,
    })
}

pub fn run_external_program_script(script: &[u8], args: &[&str]) -> anyhow::Result<()> {
    run_external_program_async(script, args)?.wait()
}
