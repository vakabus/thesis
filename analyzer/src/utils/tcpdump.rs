use std::time::Duration;

use subprocess::{unix::PopenExt, Popen, PopenConfig};

pub struct TcpDump {
    process: Popen,
}

impl TcpDump {
    pub fn start_capture(filename: &str) -> anyhow::Result<TcpDump> {
        info!("starting tcpdump");

        // tcpdump -s 0 port ftp or ssh -i eth0 -w mycap.pcap
        let popen = Popen::create(
            &["tcpdump", "-s", "0", "-i", "any", "-w", filename],
            PopenConfig::default(),
        )?;

        Ok(TcpDump { process: popen })
    }

    fn stop_by_ref(&mut self) {
        if self.process.poll().is_some() {
            error!("tcpdump exited before we stopped it");
            return;
        }

        self.process
            .send_signal(libc::SIGINT)
            .expect("failed to send signal to tcpdump");
        let wait_result = self.process.wait_timeout(Duration::from_secs(2));
        let a = wait_result
            .transpose()
            .unwrap_or_else(|| {
                _ = self.process.kill();
                self.process.wait()
            })
            .expect("failed to stop the tcpdump process");
        assert!(a.success());
    }
}

impl Drop for TcpDump {
    fn drop(&mut self) {
        self.stop_by_ref();
    }
}
