use std::os::fd::{RawFd, AsRawFd};

use pnet::{
    datalink::{self, interfaces, Channel, DataLinkSender, NetworkInterface, Config},
    packet::ethernet::{EtherTypes, MutableEthernetPacket},
    util::MacAddr,
};
use rio::Completion;

pub fn default_interface() -> Option<NetworkInterface> {
    // Get a vector with all network interfaces found
    let all_interfaces = interfaces();

    // Search for the default interface - the one that is
    // up, not loopback and has an IP.
    all_interfaces
        .into_iter()
        .find(|e| e.is_up() && !e.is_loopback() && !e.ips.is_empty())
}

pub struct RawSocket {
    tx: Box<dyn DataLinkSender>,
    count: u64,
    eth_header_cache: [u8; 14],
}

impl RawSocket {
    pub fn new() -> Self {
        let interface =
            default_interface().expect("failed to find an interface which looks like default");

        // Create a new channel, dealing with layer 2 packets
        let mut config = Config::default();
        config.write_buffer_size = 1024*1024 >> 2;
        let (tx, _) = match datalink::channel(&interface, config) {
            Ok(Channel::Ethernet(tx, rx)) => (tx, rx),
            Ok(_) => panic!("Unhandled channel type"),
            Err(e) => panic!(
                "An error occurred when creating the datalink channel: {}",
                e
            ),
        };

        let mut eth_header = [0u8; 14];
        let mut me = MutableEthernetPacket::new(&mut eth_header[..]).unwrap();
        me.set_ethertype(EtherTypes::Ipv4);
        me.set_destination(MacAddr(2, 2, 3, 4, 5, 6));
        me.set_source(MacAddr(2, 4, 6, 8, 10, 12));

        RawSocket {
            tx,
            count: 0,
            eth_header_cache: eth_header,
        }
    }

    pub fn send_ethernet_pkt_from_unique_mac(&mut self) -> anyhow::Result<()> {
        let mut ethernet_header =
            MutableEthernetPacket::new(&mut self.eth_header_cache[..]).unwrap();

        let mac_dest = self.count.to_le_bytes();
        ethernet_header.set_source(MacAddr::new(
            2,
            mac_dest[0],
            mac_dest[1],
            mac_dest[2],
            mac_dest[3],
            mac_dest[4],
        ));
        self.count = self.count.wrapping_add(1);

        self.tx.send_to(&self.eth_header_cache, None).unwrap()?;

        Ok(())
    }

    pub fn unique_mac_pkts_rapid_fire(&mut self, count: u64) -> anyhow::Result<()> {
        {
            let mut func = |pkt: &mut [u8]| {
                init_packet(pkt, self.count);
                self.count = self.count.wrapping_add(1);
            };
            self.tx.build_and_send(count as usize, self.eth_header_cache.len(), &mut func).unwrap()?;
        }

        Ok(())
    }
}

pub struct IOUringRawSocket {
    socket: RawFd,
    ring: rio::Rio,
}

impl Drop for IOUringRawSocket {
    fn drop(&mut self) {
        unsafe { libc::close(self.socket); }
    }
}


fn network_addr_to_sockaddr(
    ni: &NetworkInterface,
    storage: *mut libc::sockaddr_storage,
    proto: libc::c_int,
) -> usize {
    unsafe {
        let sll: *mut libc::sockaddr_ll = std::mem::transmute(storage);
        (*sll).sll_family = libc::AF_PACKET as libc::sa_family_t;
        if let Some(MacAddr(a, b, c, d, e, f)) = ni.mac {
            (*sll).sll_addr = [a, b, c, d, e, f, 0, 0];
        }
        (*sll).sll_protocol = (proto as u16).to_be();
        (*sll).sll_halen = 6;
        (*sll).sll_ifindex = ni.index as i32;
        std::mem::size_of::<libc::sockaddr_ll>()
    }
}

impl AsRawFd for IOUringRawSocket {
    fn as_raw_fd(&self) -> RawFd {
        self.socket
    }
}

impl IOUringRawSocket {
    pub fn new() -> std::io::Result<Self> {
        let eth_p_all: i32 = 0x0003;
        let (typ, proto) = (libc::SOCK_RAW, eth_p_all);
        let socket = unsafe { libc::socket(libc::AF_PACKET, typ, proto.to_be() as i32) };
        if socket == -1 {
            return anyhow::Result::Err(std::io::Error::last_os_error());
        }
        let mut addr: libc::sockaddr_storage = unsafe {std::mem::zeroed() };
        let len = network_addr_to_sockaddr(&default_interface().unwrap(), &mut addr, proto as i32);

        let send_addr = (&addr as *const libc::sockaddr_storage) as *const libc::sockaddr;

        // Bind to interface
        if unsafe { libc::bind(socket, send_addr, len as libc::socklen_t) } == -1 {
            let err = std::io::Error::last_os_error();
            unsafe {
                libc::close(socket);
            }
            return Err(err);
        }

        Ok(Self { socket, ring: rio::new()? })
    }

    pub fn sent_eth_pkts(&self, num: u64, count: usize) -> anyhow::Result<()> {
        let mut pkt = vec![[0u8; 16]; count];
        let mut compls = Vec::with_capacity(count);
        
        for (i, slice) in pkt.iter_mut().enumerate() {
            init_packet(slice, num+i as u64);
            let compl = self.ring.send(self, slice);
            compls.push(compl);
        }

        for c in compls.into_iter() {
            c.wait()?;
        }
        
        Ok(())
    }
}

fn init_packet(pkt: &mut [u8], initial_number: u64) {
    let mut me = MutableEthernetPacket::new(pkt).unwrap();
    me.set_ethertype(EtherTypes::Ipv4);
    me.set_destination(MacAddr(2, 2, 3, 4, 5, 6));
    let b: [u8; 8] = initial_number.to_le_bytes();
    me.set_source(MacAddr(2, b[0], b[1], b[2], b[3], b[4]));
}

fn mutate_packet(pkt: &mut [u8]) {
    let mut ethernet_header = MutableEthernetPacket::new(pkt).unwrap();

    let mut source = ethernet_header.get_source();

    let mut carry = false;
    (source.5, carry) = source.5.carrying_add(1, carry);
    (source.4, carry) = source.4.carrying_add(1, carry);
    (source.3, carry) = source.3.carrying_add(1, carry);
    (source.2, carry) = source.2.carrying_add(1, carry);
    (source.1, carry) = source.1.carrying_add(1, carry);
    (source.0, _)     = source.0.carrying_add(1, carry);

    ethernet_header.set_source(source);
}
