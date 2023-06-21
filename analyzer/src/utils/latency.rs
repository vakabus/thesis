use core::panic;
use std::{
    net::{IpAddr, Ipv4Addr, UdpSocket},
    time::{Duration, Instant},
};

use anyhow::{anyhow, Context};
use serde::Serialize;
use subprocess::{Exec, Redirection};

use super::{
    clock_ns,
    collector::{CSVCollector, Monitor},
};

/// turns this line:
/// >  64 bytes from 127.0.0.1: icmp_seq=1 ttl=64 time=0.053 ms
/// into Duration object 53us
fn parse_ping_output_line(line: &str) -> anyhow::Result<Duration> {
    if !line.starts_with("64 bytes from ") {
        return Err(anyhow!(
            "ping result line starts with unexpected data: {}",
            line
        ));
    }

    let mut time = line.split(' ').rev().nth(1).unwrap()[5..].split('.');
    let ms = time.next().unwrap().parse::<usize>().unwrap();
    let fractional = time.next().unwrap_or("0");
    let duration_us: usize = ms * 1000
        + usize::pow(10, (3 - fractional.len()) as u32) * fractional.parse::<usize>().unwrap();

    Ok(Duration::from_micros(duration_us as u64))
}

pub fn ping(addr: IpAddr) -> anyhow::Result<Duration> {
    let child = Exec::cmd("ping")
        .args(&["-c", "1", "-w", "1", &addr.to_string()])
        .stdout(Redirection::Pipe)
        .capture()
        .unwrap();

    if !child.success() {
        Err(anyhow!(
            "ping command exited with non-zero exit code {:?}",
            child.exit_status
        ))
    } else {
        let out = child.stdout_str();
        let res = out.lines().nth(1).unwrap();
        parse_ping_output_line(res)
    }
}

#[derive(Serialize)]
pub struct PingStat {
    ts: u64,
    latency_us: u64,
}
pub struct PingMonitor {
    addr: IpAddr,
}
impl Monitor for PingMonitor {
    type Stats = PingStat;

    fn new() -> anyhow::Result<Self>
    where
        Self: Sized,
    {
        Ok(PingMonitor {
            addr: IpAddr::V4(Ipv4Addr::new(192, 168, 1, 221)),
        })
    }

    fn collect(&mut self) -> anyhow::Result<Self::Stats> {
        match ping(self.addr) {
            Ok(d) => Ok(PingStat {
                ts: clock_ns()?,
                latency_us: d.as_micros() as u64,
            }),
            Err(e) => {
                warn!("ping failed: {}", e);
                Ok(PingStat {
                    ts: clock_ns()?,
                    latency_us: u64::MAX,
                })
            }
        }
    }
}

pub fn ping_multiple(count: usize, addr: IpAddr) -> Result<Vec<Duration>, anyhow::Error> {
    // the pings are 10ms apart, that should be enough for the kernel to create the rule
    let child = Exec::cmd("ping")
        .args(&[
            "-c",
            &format!("{}", count),
            "-i",
            "0.01",
            "-w",
            "1",
            &addr.to_string(),
        ])
        .stdout(Redirection::Pipe)
        .capture()
        .unwrap();

    if !child.success() {
        Err(anyhow::Error::msg(
            "ping command exited with non-zero exit code",
        ))
    } else {
        let out = child.stdout_str();
        let mut lines = out.lines().skip(1); // header

        let mut res = Vec::with_capacity(count);
        for i in 0..count {
            let line = lines
                .next()
                .context(format!("missing {}th ping stats", i + 1))?;
            res.push(parse_ping_output_line(line)?);
        }

        Ok(res)
    }
}

pub fn ping_twice(addr: IpAddr) -> Result<(Duration, Duration), anyhow::Error> {
    let vec = ping_multiple(2, addr)?;
    Ok((vec[0], vec[1]))
}

pub fn dns_lookup(server: IpAddr) -> Duration {
    // lookup for `tapir.lan` recorded in Wireshark
    let payload: [u8; 27] = [
        0x87, 0x58, 0x01, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x05, 0x74, 0x61,
        0x70, 0x69, 0x72, 0x03, 0x6c, 0x61, 0x6e, 0x00, 0x00, 0x01, 0x00, 0x01,
    ];

    let mut resbuffer = [0u8; 1024];

    let socket = UdpSocket::bind("0.0.0.0:0").unwrap();
    socket
        .send_to(&payload, (server, 53))
        .expect("failed to send data");
    let after_send = Instant::now();

    // receive packets until we get one back from the server
    loop {
        let result = socket.recv_from(&mut resbuffer);
        if let Ok((_size, addr)) = result {
            if addr.ip() == server && addr.port() == 53 {
                // we don't care about the content of the reply
                break;
            } else {
                warn!("received unexpected packet from {:?}", addr);
            }
        } else {
            panic!("failed to receive udp packet");
        }
    }
    let after_recv = Instant::now();

    after_recv.duration_since(after_send)
}

pub type PingCollector = CSVCollector<PingMonitor>;

#[cfg(test)]
mod test {
    use crate::utils::latency::dns_lookup;
    use std::{net::IpAddr, str::FromStr};

    #[test]
    fn test_dns_request() {
        let duration = dns_lookup(IpAddr::from_str("1.1.1.1").unwrap());
        println!("lookup duration {:?}", duration);
        panic!();
    }
}
