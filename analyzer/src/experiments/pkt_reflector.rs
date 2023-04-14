//! Ethernet echo server based on the example in the pnet library.
//! https://docs.rs/pnet/latest/pnet/

extern crate pnet;

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use anyhow::Result;
use clap::Parser;
use pnet::datalink;
use pnet::datalink::Channel::Ethernet;
use pnet::packet::ethernet::{EtherTypes, EthernetPacket, MutableEthernetPacket};
use pnet::packet::ip::{IpNextHeaderProtocol, IpNextHeaderProtocols};
use pnet::packet::ipv4::MutableIpv4Packet;
use pnet::packet::ipv6::MutableIpv6Packet;
use pnet::packet::udp::MutableUdpPacket;
use pnet::packet::{MutablePacket, Packet};

use crate::utils::raw_socket::default_interface;

#[derive(Parser, Debug)]
pub struct ReflectorArgs {}

// Invoke as echo <interface name>
pub fn run(_arg: ReflectorArgs) -> Result<()> {
    let ipt = iptables::new(false).expect("failed to initialize iptables");
    ipt.append("filter", "INPUT", "-j DROP")
        .expect("failed to add rule");
    info!("blocking all input traffic");

    let interface = default_interface().expect("no default interface");
    // Create a new channel, dealing with layer 2 packets
    let (mut tx, mut rx) = match datalink::channel(&interface, Default::default()) {
        Ok(Ethernet(tx, rx)) => (tx, rx),
        Ok(_) => panic!("Unhandled channel type"),
        Err(e) => panic!(
            "An error occurred when creating the datalink channel: {}",
            e
        ),
    };
    info!("Echo server running! SIGINT to stop...");

    let stop = Arc::new(AtomicBool::new(false));
    signal_hook::flag::register(signal_hook::consts::SIGINT, Arc::clone(&stop)).unwrap();
    while !stop.load(Ordering::Relaxed) {
        match rx.next() {
            Ok(packet) => {
                let packet = EthernetPacket::new(packet).unwrap();

                // Constructs a single packet, the same length as the the one received,
                // using the provided closure. This allows the packet to be constructed
                // directly in the write buffer, without copying. If copying is not a
                // problem, you could also use send_to.
                //
                // The packet is sent once the closure has finished executing.
                tx.build_and_send(1, packet.packet().len(), &mut |new_packet| {
                    let mut new_packet = MutableEthernetPacket::new(new_packet).unwrap();

                    // Create a clone of the original packet
                    new_packet.clone_from(&packet);

                    // Switch the source and destination
                    new_packet.set_source(packet.get_destination());
                    new_packet.set_destination(packet.get_source());

                    // try to swap higher level dest and src
                    match new_packet.get_ethertype() {
                        EtherTypes::Ipv4 => {
                            let opt_ip = MutableIpv4Packet::new(new_packet.payload_mut());
                            if let Some(mut ip) = opt_ip {
                                let dest = ip.get_destination();
                                ip.set_destination(ip.get_source());
                                ip.set_source(dest);

                                swap_l4_src_dest(ip.get_next_level_protocol(), ip.payload_mut());
                            } else {
                                warn!("invalid ipv4 packet");
                            }
                        }
                        EtherTypes::Ipv6 => {
                            let opt_ip = MutableIpv6Packet::new(new_packet.payload_mut());
                            if let Some(mut ip) = opt_ip {
                                let dest = ip.get_destination();
                                ip.set_destination(ip.get_source());
                                ip.set_source(dest);

                                swap_l4_src_dest(ip.get_next_header(), ip.payload_mut());
                            } else {
                                warn!("invalid ipv6 packet");
                            }
                        }
                        _ => {
                            // just do nothing
                        }
                    };
                });
            }
            Err(e) => {
                // If an error occurs, we can handle it here
                panic!("An error occurred while reading: {}", e);
            }
        }
    }

    info!("cleaning iptables rules");
    ipt.delete("filter", "INPUT", "-j DROP")
        .expect("failed to delete iptables rule");
    Ok(())
}

fn swap_l4_src_dest(prot: IpNextHeaderProtocol, payload: &mut [u8]) {
    match prot {
        IpNextHeaderProtocols::Udp => {
            let opt_pkt = MutableUdpPacket::new(payload);
            if let Some(mut pkt) = opt_pkt {
                let dest = pkt.get_destination();
                pkt.set_destination(pkt.get_source());
                pkt.set_source(dest);
            } else {
                warn!("invalid UDP");
            }
        }
        IpNextHeaderProtocols::Tcp => {
            /* We could swap it for TCP as well, but that would be weird. TCP connections are "oriented",
            and the sender would have to also listen on the IP,port pair he is sending from? That's unusual.
            If we do not swap the ports, the sender can open one listening socket and one sending. And use the
            listening socket port to reflect it directly to the listening socket.

            ==> so no swapping for tcp */
        }
        _ => {
            // do nothing
        }
    };
}
