use std::{net::{UdpSocket, Ipv4Addr, TcpStream}, io::{Write, Read}, time::Duration, sync::{mpsc::{channel, Receiver, Sender}, atomic::{AtomicBool, Ordering}, Arc}, thread::{JoinHandle, self}, collections::BTreeSet};

use anyhow::{bail, Result};
use serde::Serialize;

use super::{
    clock_ns,
    collector::{CSVCollector, MultiMonitor, Monitor},
};



#[derive(Debug, Serialize)]
pub struct Datapoint {
    ts: u64,
    latency_ns: u64
}

const MSG: [u8; 1] = [42u8];

pub struct UdpRRMonitor {
    socket: UdpSocket,
    receiver: Receiver<(u64, u64)>,
    stop_flag: Arc<AtomicBool>,
    recv_thread: Option<JoinHandle<()>>,
    sent: BTreeSet<u64>,
}

impl UdpRRMonitor {
    fn receive_thread(stop_flag: Arc<AtomicBool>, socket: UdpSocket, sender: Sender<(u64,u64)>) {
        while ! stop_flag.load(Ordering::Relaxed) {
            let mut buf = [0u8; 8];
            socket.set_read_timeout(Some(Duration::from_millis(200))).unwrap(); // more than the expected measurement interval
            match socket.recv(&mut buf) {
                Ok(size) => {
                    if size == 8 {
                        let recv_time = clock_ns().unwrap();
                        sender.send((u64::from_le_bytes(buf), recv_time)).unwrap();
                    } else {
                        warn!("UDP packet of unexpected size {}", size);
                    }
                },
                Err(e) => {
                    warn!("packet recv error: {}", e);
                }
            }
        }
    }
}


impl MultiMonitor for UdpRRMonitor {
    type Stats = Datapoint;

    fn new() -> Result<Self> {
        let sock = UdpSocket::bind("0.0.0.0:0")?;
        sock.connect("reflector.default.svc.cluster.local:80")?;
        let sock_clone = sock.try_clone()?;

        let (sender, receiver) = channel();
        let stop_flag = Arc::new(AtomicBool::new(false));
        let stop_flag_clone = stop_flag.clone();
        
        let handle = thread::spawn(|| {
            UdpRRMonitor::receive_thread(stop_flag_clone, sock, sender);
        });
        Ok(UdpRRMonitor{socket: sock_clone, receiver, stop_flag: stop_flag, recv_thread: Some(handle), sent: BTreeSet::new()})
    }

    fn collect_multiple(&mut self) -> Result<Vec<Self::Stats>> {
        // send new packet
        let before_send = clock_ns()?;
        self.socket.send(&before_send.to_le_bytes())?;
        self.sent.insert(before_send); // store info about what we have sent to track dropped packets


        // collect all received packets
        let mut res = vec![];
        loop {
            let r = self.receiver.try_recv();
            match r {
                Ok((t1, t2)) => {
                    let ts = u64::min(t1, t2);
                    let latency_ns = u64::abs_diff(t1, t2);
                    res.push(Self::Stats {
                        ts,
                        latency_ns
                    });
                    if ! self.sent.remove(&ts) {
                        panic!("removing ts that we did not send");
                    }
                },
                Err(err) => {
                    break;
                }
            }
        }

        // detect dropped packets
        const DROPPED_THRESHOLD_NS: u64 = 15_000_000_000;  // 15 sec
        for ts in self.sent.iter() {
            if u64::abs_diff(before_send, *ts) > DROPPED_THRESHOLD_NS {
                res.push(Self::Stats {
                    ts: *ts,
                    latency_ns: u64::MAX
                });
            } else {
                // we are iterating in ascending order, so nothing following will be expired
                break;
            }
        }

        Ok(res)
    }
}

impl Drop for UdpRRMonitor {
    fn drop(&mut self) {
        self.stop_flag.store(true, Ordering::Relaxed);
        self.recv_thread.take().unwrap().join().expect("joining the recv thread of UdpRRMonitor failed");
    }
}

pub struct TcpRRMonitor {
    socket: TcpStream,
}

impl Monitor for TcpRRMonitor {
    type Stats = Datapoint;

    fn new() -> Result<Self> {
        let sock = TcpStream::connect("reflector.default.svc.cluster.local:80")?;
        Ok(TcpRRMonitor {socket: sock})
    }

    fn collect(&mut self) -> anyhow::Result<Datapoint> {
        let before_send = clock_ns()?;
        self.socket.write(&MSG)?;
        self.socket.flush()?;

        let mut resp_buff = [0u8; MSG.len()];
        self.socket.read(&mut resp_buff)?;
        let after_recv = clock_ns()?;

        Ok(Datapoint {
            ts: clock_ns()?,
            latency_ns: after_recv - before_send,
        })
    }
}

pub type UdpRRCollector = CSVCollector<UdpRRMonitor>;
pub type TcpRRCollector = CSVCollector<UdpRRMonitor>;
