from scapy.all import *
from time import sleep
import random

# fix random seed for reproducibility
random.seed("number of flow rules to the moon :)")

# simulate macof (we know that should generate flow rules)
mac1 = RandMAC()
mac2 = RandMAC()
sendp(Ether(src=mac1, dst=mac2)/ARP(op=2, psrc="0.0.0.0", hwsrc=mac1, hwdst=mac2)/Padding(load="A"*18), count=1000)
sleep(11)

# random MAC address
sendp( Ether(src=RandMAC(), dst=RandMAC()) / IP(src="192.168.1.1", dst="192.168.1.1") / Padding(load="A*32"), count=1000)
sleep(11)

# random MAC address in dst only
sendp( Ether(dst=RandMAC()) / IP(src="192.168.1.1", dst="192.168.1.1") / Padding(load="A*32"), count=1000)
sleep(11)

# random MAC address in src only
sendp( Ether(src=RandMAC()) / IP(src="192.168.1.1", dst="192.168.1.1") / Padding(load="A*32"), count=1000)
sleep(11)

# random IP address src
send(IP(src=RandIP(), dst="192.168.1.1"), count=1000)
sleep(11)

# random IP address dst
send(IP(src="192.168.1.1", dst=RandIP()), count=1000)
sleep(11)

# random IP address both
send(IP(src=RandIP(), dst=RandIP()), count=1000)
sleep(11)


# random ip headers
send(fuzz(IP(src="192.168.1.1", dst="192.168.1.1")), count=1000)
sleep(11)