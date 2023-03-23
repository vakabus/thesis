#!/usr/bin/env python3

"""
struct sw_flow_key {
	u8 tun_opts[IP_TUNNEL_OPTS_MAX];
	u8 tun_opts_len;
	struct ip_tunnel_key tun_key;	/* Encapsulating tunnel key. */
	struct {
		u32	priority;	/* Packet QoS priority. */
		u32	skb_mark;	/* SKB mark. */
		u16	in_port;	/* Input switch port (or DP_MAX_PORTS). */
	} __packed phy; /* Safe when right after 'tun_key'. */
	u8 mac_proto;			/* MAC layer protocol (e.g. Ethernet). */                       <------------  NOT INTERESTING https://elixir.bootlin.com/linux/v6.2.6/source/net/openvswitch/flow.c#L983
	u8 tun_proto;			/* Protocol of encapsulating tunnel. */
	u32 ovs_flow_hash;		/* Datapath computed hash value.  */
	u32 recirc_id;			/* Recirculation ID.  */
	struct {
		u8     src[ETH_ALEN];	/* Ethernet source address. */                              <------------- interesting, easy to test
		u8     dst[ETH_ALEN];	/* Ethernet destination address. */                         <------------- interesting, easy to test
		struct vlan_head vlan;
		struct vlan_head cvlan;
		__be16 type;		/* Ethernet frame type. */
	} eth;
	/* Filling a hole of two bytes. */
	u8 ct_state;
	u8 ct_orig_proto;		/* CT original direction tuple IP
					 * protocol.
					 */
	union {
		struct {
			u8     proto;	/* IP protocol or lower 8 bits of ARP opcode. */               <---------------
			u8     tos;	    /* IP ToS. */                                                  <---------------
			u8     ttl;	    /* IP TTL/hop limit. */                                        <---------------
			u8     frag;	/* One of OVS_FRAG_TYPE_*. */                                  <------------  NOT INTERESTING
		} ip;
	};
	u16 ct_zone;			/* Conntrack zone. */
	struct {
		__be16 src;		/* TCP/UDP/SCTP source port. */                                    <-------------
		__be16 dst;		/* TCP/UDP/SCTP destination port. */                               <--------------
		__be16 flags;		/* TCP flags. */                                               <---------------
	} tp;
	union {
		struct {
			struct {
				__be32 src;	/* IP source address. */                                       <-------------
				__be32 dst;	/* IP destination address. */                                  <-------------
			} addr;
			union {
				struct {
					__be32 src;
					__be32 dst;
				} ct_orig;	/* Conntrack original direction fields. */
				struct {
					u8 sha[ETH_ALEN];	/* ARP source hardware address. */                 <------
					u8 tha[ETH_ALEN];	/* ARP target hardware address. */                 <------
				} arp;
			};
		} ipv4;
		struct {
			struct {
				struct in6_addr src;	/* IPv6 source address. */                         <-------
				struct in6_addr dst;	/* IPv6 destination address. */                    <-------
			} addr;
			__be32 label;			/* IPv6 flow label. */                                 <------
			u16 exthdrs;	/* IPv6 extension header flags */                              <-------
			union {
				struct {
					struct in6_addr src;
					struct in6_addr dst;
				} ct_orig;	/* Conntrack original direction fields. */
				struct {
					struct in6_addr target;	/* ND target address. */                       <-------
					u8 sll[ETH_ALEN];	/* ND source link layer address. */                <-------
					u8 tll[ETH_ALEN];	/* ND target link layer address. */                <-------
				} nd;
			};
		} ipv6;
		struct {                                                                                   ???????????????? MPLS ????
			u32 num_labels_mask;    /* labels present bitmap of effective length MPLS_LABEL_DEPTH */
			__be32 lse[MPLS_LABEL_DEPTH];     /* label stack entry  */
		} mpls;

		struct ovs_key_nsh nsh;         /* network service header */
	};
	struct {
		/* Connection tracking fields not packed above. */
		struct {
			__be16 src;	/* CT orig tuple tp src port. */
			__be16 dst;	/* CT orig tuple tp dst port. */
		} orig_tp;
		u32 mark;
		struct ovs_key_ct_labels labels;
	} ct;

} __aligned(BITS_PER_LONG/8); /* Ensure that we can do comparisons as longs. */
"""

from scapy.all import *
from time import sleep
import random
import time
import json
import sys

# fix random seed for reproducibility
random.seed("number of flow rules to the moon :)")

if len(sys.argv) != 2:
    print("ERROR: Invalid number of arguments. Expected:", file=sys.stderr)
    print("\t[TAG_FILE]", file=sys.stderr)
    sys.exit(1)


tag_file = open(sys.argv[1], 'w')


def tag(t: str):
    print("testing:", t)
    send(IP() / UDP(sport=59652, dport=9876) / Raw(load=f'{{"tag":"{t}"}}'))
    time_ns = int(time.clock_gettime(time.CLOCK_MONOTONIC)*1_000_000_000)
    print(json.dumps({"tag": t, "ts": time_ns}), file=tag_file)


tag("baseline")
sleep(11)

# simulate macof (we know that should generate flow rules)
tag("macof sim => Ether(src,dst)/ARP")
mac1 = RandMAC()
mac2 = RandMAC()
sendp(Ether(src=mac1, dst=mac2)/ARP(op=2, psrc="0.0.0.0", hwsrc=mac1, hwdst=mac2)/Padding(load="A"*18), count=1000)
sleep(11)

# random MAC addresses in IP packets
tag("Ether(src,dst)")
sendp( Ether(src=RandMAC(), dst=RandMAC()) / IP(src="192.168.1.1", dst="192.168.1.1") / Padding(load="A"*32), count=1000)
sleep(11)

# random MAC address IP packet, dst only
tag("Ether(dst)")
sendp( Ether(dst=RandMAC()) / IP(src="192.168.1.1", dst="192.168.1.1") / Padding(load="A"*32), count=1000)
sleep(11)

# random MAC address IP packet, src only
tag("Ether(src)")
sendp( Ether(src=RandMAC()) / IP(src="192.168.1.1", dst="192.168.1.1") / Padding(load="A"*32), count=1000)
sleep(11)

# random MAC address IP packet, src only, but only "locally administered unicast"                                              <------------ GOOD
tag("Ether(dst=02:*)")
sendp( Ether(src=RandMAC("02")) / IP(src="192.168.1.1", dst="192.168.1.1") / Padding(load="A"*32), count=1000)
sleep(11)

# random MAC address IP packet, src only, but only "universally administered unicast"                                          <------------ GOOD
tag("Ether(dst=04:*)")
sendp( Ether(src=RandMAC("04")) / IP(src="192.168.1.1", dst="192.168.1.1") / Padding(load="A"*32), count=1000)
sleep(11)

# random MAC address IP packet, src only, but only "locally administered multicast"
tag("Ether(dst=03:*)")
sendp( Ether(src=RandMAC("03")) / IP(src="192.168.1.1", dst="192.168.1.1") / Padding(load="A"*32), count=1000)
sleep(11)

# random MAC address IP packet, src only, but only "universally administered multicast"
tag("Ether(dst=01:*)")
sendp( Ether(src=RandMAC("01")) / IP(src="192.168.1.1", dst="192.168.1.1") / Padding(load="A"*32), count=1000)
sleep(11)


# random IP version
tag("IP(version)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst="10.244.1.1", version=RandByte()), count=1000)
sleep(11)

# random IP TOS
tag("IP(tos)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst="10.244.1.1", tos=RandByte()), count=1000)
sleep(11)

# random IP TTL
tag("IP(ttl)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst="10.244.1.1", ttl=RandByte()), count=1000)
sleep(11)

# random identification
tag("IP(id)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst="10.244.1.1", id=RandShort()), count=1000)
sleep(11)

# random flags
tag("IP(flags)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst="10.244.1.1", flags=RandNum(0, 7)), count=1000)
sleep(11)

# random flags and fragment offset
tag("IP(flags,frag)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst="10.244.1.1", flags=RandNum(0, 7), frag=RandNum(0, 2**12-1)), count=1000)
sleep(11)


# random protocol (Padding is there so that there is some actual data following the IP packet )
tag("IP(proto)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst="10.244.1.1", proto=RandByte()) / Padding(load="A"*48), count=1000)
sleep(11)

# random IP address src
tag("IP(src)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(src=RandIP(), dst="192.168.1.1"), count=1000)
sleep(11)

# random IP address dst
tag("IP(dst)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(src="192.168.1.1", dst=RandIP()), count=1000)
sleep(11)

# random IP address both
tag("IP(dst,src)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(src=RandIP(), dst=RandIP()), count=1000)
sleep(11)

# random IP src in the subnet of cluster pod network 10.244.0.0/16
# some dst address has to be specified, otherwise it's gonna go to 127.0.0.1
tag("IP(src in 10.244.0.0/16)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(src=RandIP("10.244.0.0/16"), dst="192.168.1.1"), count=1000)
sleep(11)

# random IP dst in the subnet of cluster pod network 10.244.0.0/16
tag("IP(dst in 10.244.0.0/16)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("10.244.0.0/16")), count=1000)
sleep(11)

# random IP dst in the subnet of cluster pod network 10.244.1.0/24
tag("IP(dst in 10.244.1.0/24)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("10.244.1.0/24")), count=1000)
sleep(11)

tag("IP(dst in 0.0.0.0/8")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("0.0.0.0/8")), count=1000)
sleep(11)

tag("IP(dst in 10.0.0.0/8")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("10.0.0.0/8")), count=1000)
sleep(11)

tag("IP(dst in 100.64.0.0/10")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("100.64.0.0/10")), count=1000)
sleep(11)

tag("IP(dst in 127.0.0.0/8")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("127.0.0.0/8")), count=1000)
sleep(11)

tag("IP(dst in 169.254.0.0/16")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("169.254.0.0/16")), count=1000)
sleep(11)

tag("IP(dst in 172.16.0.0/12")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("172.16.0.0/12")), count=1000)
sleep(11)

tag("IP(dst in 192.0.0.0/24")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("192.0.0.0/24")), count=1000)
sleep(11)

tag("IP(dst in 192.0.2.0/24")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("192.0.2.0/24")), count=1000)
sleep(11)

tag("IP(dst in 192.88.99.0/24")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("192.88.99.0/24")), count=1000)
sleep(11)

tag("IP(dst in 192.168.0.0/16")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("192.168.0.0/16")), count=1000)
sleep(11)

tag("IP(dst in 198.18.0.0/15")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("198.18.0.0/15")), count=1000)
sleep(11)

tag("IP(dst in 198.51.100.0/24")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("198.51.100.0/24")), count=1000)
sleep(11)

tag("IP(dst in 203.0.113.0/24")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("203.0.113.0/24")), count=1000)
sleep(11)

tag("IP(dst in 224.0.0.0/4")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("224.0.0.0/4")), count=1000)
sleep(11)

tag("IP(dst in 233.252.0.0/24")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("233.252.0.0/24")), count=1000)
sleep(11)

tag("IP(dst in 240.0.0.0/4")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("240.0.0.0/4")), count=1000)
sleep(11)

tag("IP(dst in 255.255.255.255/32")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst=RandIP("255.255.255.255/32")), count=1000)
sleep(11)

tag("IPv6(tc)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(dst="2001:67c:2190:1506:30bb:feff:feeb:b72f" ,tc=RandByte()), count=1000)
sleep(11)

tag("IPv6(fl)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(dst="2001:67c:2190:1506:30bb:feff:feeb:b72f" ,fl=RandNum(0, 2**20-1)), count=1000)
sleep(11)

tag("IPv6()/IPv6ExtHdrDestOpt()")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(dst="2001:67c:2190:1506:30bb:feff:feeb:b72f")/IPv6ExtHdrHopByHop() / fuzz(IPv6ExtHdrDestOpt()), count=1000)
sleep(11)

tag("IPv6()/IPv6ExtHdrDestOpt()")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(dst="2001:67c:2190:1506:30bb:feff:feeb:b72f")/IPv6ExtHdrHopByHop() / fuzz(IPv6ExtHdrDestOpt()), count=1000)
sleep(11)

tag("IPv6()/IPv6ExtHdrRouting()")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(dst="2001:67c:2190:1506:30bb:feff:feeb:b72f")/IPv6ExtHdrHopByHop() / fuzz(IPv6ExtHdrRouting()), count=1000)
sleep(11)

tag("IPv6()/IPv6ExtHdrSegmentRouting()")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(dst="2001:67c:2190:1506:30bb:feff:feeb:b72f")/IPv6ExtHdrHopByHop() / fuzz(IPv6ExtHdrSegmentRouting()), count=1000)
sleep(11)

tag("IPv6(dst)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(dst=RandIP6()), count=1000)
sleep(11)

tag("IPv6(src)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(src=RandIP6()), count=1000)
sleep(11)

tag("IPv6(dst,src)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(src=RandIP6(), dst=RandIP6()), count=1000)
sleep(11)

tag("IP()/UDP(dport)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst="10.244.1.1")/ UDP(dport=RandShort(), sport=2222), count=1000)
sleep(11)

tag("IP()/UDP(sport)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst="10.244.1.1")/ UDP(dport=2222, sport=RandShort()), count=1000)
sleep(11)

tag("IP()/UDP(dport, sport)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst="10.244.1.1")/ UDP(dport=RandShort(), sport=RandShort()), count=1000)
sleep(11)

tag("ARP(op)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / ARP(op=RandShort(), hwdst="ff:ee:dd:cc:bb:aa", pdst="10.11.12.13"), count=1000)
sleep(11)

tag("ARP(hwtype)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / ARP(hwtype=RandShort(), hwdst="ff:ee:dd:cc:bb:aa", pdst="10.11.12.13"), count=1000)
sleep(11)

tag("ARP(hwsrc)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / ARP(hwsrc=RandMAC(), hwdst="ff:ee:dd:cc:bb:aa", pdst="10.11.12.13"), count=1000)
sleep(11)

tag("ARP(hwdst)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / ARP(hwdst=RandMAC()), count=1000)
sleep(11)

tag("ARP(psrc)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / ARP(psrc=RandIP(), hwdst="ff:ee:dd:cc:bb:aa", pdst="10.11.12.13"), count=1000)
sleep(11)

tag("ARP(pdst)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / ARP(pdst=RandIP(), hwdst="ff:ee:dd:cc:bb:aa"), count=1000)
sleep(11)

tag("ICMPv6ND_RS")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(dst="2001:67c:2190:1506:30bb:feff:feeb:b72f") / ICMPv6ND_RS(code=RandByte(), res=RandInt()), count=1000)
sleep(11)

tag("ICMPv6ND_Redirect")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(dst="2001:67c:2190:1506:30bb:feff:feeb:b72f") / ICMPv6ND_Redirect(code=RandByte(), tgt=RandIP6(), dst=RandIP6()), count=1000)
sleep(11)

tag("ICMPv6ND_RA")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(dst="2001:67c:2190:1506:30bb:feff:feeb:b72f") / ICMPv6ND_RA(chlim=RandByte(), M=RandChoice(0,1),O=RandChoice(0,1), H=RandChoice(0,1), P=RandChoice(0,1), res=RandChoice(0,1,2,3), code=RandByte()), count=1000)
sleep(11)

tag("ICMPv6ND_NS")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(dst="2001:67c:2190:1506:30bb:feff:feeb:b72f") / ICMPv6ND_NS(code=RandByte(), res=RandInt(), tgt=RandIP6()), count=1000)
sleep(11)

tag("ICMPv6ND_NA")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IPv6(dst="2001:67c:2190:1506:30bb:feff:feeb:b72f") / ICMPv6ND_NA(code=RandByte(), R=RandChoice(0,1), S=RandChoice(0,1), O=RandChoice(0,1), res=RandNum(0, 2**29-1), tgt=RandIP6()), count=1000)
sleep(11)

tag("end")
tag_file.close()