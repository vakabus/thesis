use pnet::{
    datalink::{self, interfaces, Channel, DataLinkSender, NetworkInterface},
    packet::ethernet::{EtherTypes, MutableEthernetPacket},
    util::MacAddr,
};

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
        let (tx, _) = match datalink::channel(&interface, Default::default()) {
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
}
