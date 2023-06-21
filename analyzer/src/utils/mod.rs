use std::{
    thread::sleep,
    time::{Duration, Instant},
};

use anyhow::bail;
use nix::sys::{
    signal::{sigprocmask, SigmaskHow},
    signalfd::SigSet,
};
use signal_hook::{
    iterator::{exfiltrator::SignalOnly, SignalsInfo},
    low_level::signal_name,
};

pub mod collector;
pub mod external_prog;
pub mod latency;
pub mod loadavg;
pub mod ovs;
pub mod raw_socket;
pub mod results_uploader;
pub mod rr;
pub mod tcpdump;
pub mod vswitchd_monitor;

pub fn dump_file(name: &str, ext: &str) -> String {
    format!("{}_{}.{}", name, chrono::Local::now().to_rfc3339(), ext)
}

pub fn clock_ns() -> anyhow::Result<u64> {
    let clck = nix::time::clock_gettime(nix::time::ClockId::CLOCK_MONOTONIC)?;

    Ok((clck.tv_nsec() as u64).wrapping_add((clck.tv_sec() as u64).wrapping_mul(1_000_000_000)))
}

pub fn wait_for_signal(signal: i32) -> anyhow::Result<()> {
    let mut signals = SignalsInfo::<SignalOnly>::new(vec![signal])?;
    debug!(
        "Waiting for signal {}",
        signal_hook::low_level::signal_name(signal).unwrap()
    );
    if let Some(sig) = (&mut signals).into_iter().next() {
        if sig == signal {
            return Ok(());
        } else {
            bail!("received signal {} when expecting {}", sig, signal);
        };
    }

    bail!("ehm, this should never happen");
}

pub fn wait_for_signal_or_timeout(expect: i32, timeout: Duration) -> anyhow::Result<()> {
    let mut signals = SignalsInfo::<SignalOnly>::new(vec![expect])?;
    debug!("Waiting for signal {}", signal_name(expect).unwrap());

    let start = Instant::now();
    while start + timeout > Instant::now() {
        // check signals
        for sig in signals.pending() {
            if sig == expect {
                debug!("signal {} received", signal_name(sig).unwrap());
                return Ok(());
            } else {
                bail!(
                    "received signal {} when expecting {}",
                    signal_name(sig).unwrap(),
                    signal_name(expect).unwrap()
                );
            };
        }

        // wait
        let wait = Duration::min(Instant::now() - start + timeout, Duration::from_millis(250));
        sleep(wait);
    }

    debug!("timeout reached");
    // timeout
    Ok(())
}

pub fn with_blocked_signals<R: Sized, T: FnOnce() -> R>(func: T) -> R {
    let mut set = SigSet::empty();
    sigprocmask(SigmaskHow::SIG_BLOCK, Some(&SigSet::all()), Some(&mut set))
        .expect("blocking of signals failed");
    let ret = func();
    sigprocmask(SigmaskHow::SIG_SETMASK, Some(&set), None).expect("unblocking of signals failed");
    ret
}

pub fn block_signals() {
    sigprocmask(SigmaskHow::SIG_BLOCK, Some(&SigSet::all()), None)
        .expect("blocking of signals failed");
}
