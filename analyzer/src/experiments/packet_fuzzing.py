from scapy.all import *
from time import sleep
import random

# fix random seed for reproducibility
random.seed("number of flow rules to the moon :)")


def tag(t: str):
    print("testing:", t)
    send(IP() / UDP(sport=59652, dport=9876) / Raw(load=f'{{"tag":"{t}"}}'))

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


# random IP TOS
tag("IP(tos)")
sendp(Ether(dst="aa:bb:cc:dd:ee:ff") / IP(dst="10.244.1.1", tos=RandByte()), count=1000)
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
tag("IP(src)")
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
