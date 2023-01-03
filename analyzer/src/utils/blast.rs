use std::net::{Ipv4Addr, UdpSocket};

pub fn blast_udp_ipv4(start_addr: Ipv4Addr, count: u32) {
    let numerical_addr: u32 = start_addr.into();

    let socket = UdpSocket::bind("0.0.0.0:0").unwrap();
    let payload = "Hello!".as_bytes();

    for addr in numerical_addr..numerical_addr + count {
        let ip = Ipv4Addr::from(addr);

        // send to port 9000, because why not
        socket.send_to(payload, (ip, 9000)).unwrap();
    }
}

#[test]
fn test_blast_runs() {
    blast_udp_ipv4(Ipv4Addr::new(198, 18, 0, 0), 10000);
}
