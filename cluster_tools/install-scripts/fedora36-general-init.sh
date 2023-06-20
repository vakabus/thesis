#!/bin/bash

set -e
export PATH=/usr/local/bin:/usr/bin:/usr/local/sbin:/usr/sbin

# wait for full startup
echo "Waiting for full system startup..."
while [[ "$(systemctl show --property=SystemState)" != "SystemState=running" ]]; do
    sleep 1
done



function install_docker {
    sudo dnf -y install dnf-plugins-core
    sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo

    sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo dnf install -y https://github.com/Mirantis/cri-dockerd/releases/download/v0.3.1/cri-dockerd-0.3.1-3.fc36.x86_64.rpm

    sudo systemctl enable --now docker
    sudo systemctl enable --now cri-docker
}

function install_kubernetes {
    cat <<EOF | sudo tee /etc/yum.repos.d/kubernetes.repo
[kubernetes]
name=Kubernetes
baseurl=https://packages.cloud.google.com/yum/repos/kubernetes-el7-\$basearch
enabled=1
gpgcheck=1
gpgkey=https://packages.cloud.google.com/yum/doc/rpm-package-key.gpg
exclude=kubelet kubeadm kubectl
EOF

    # Set SELinux in permissive mode (effectively disabling it)
    sudo setenforce 0
    sudo sed -i 's/^SELINUX=enforcing$/SELINUX=permissive/' /etc/selinux/config
    sudo yum install -y kubelet kubeadm kubectl kubernetes-cni --disableexcludes=kubernetes
    sudo systemctl enable --now kubelet

    # configure system
    cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF

    sudo modprobe overlay
    sudo modprobe br_netfilter

    # sysctl params required by setup, params persist across reboots
    cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF

    # Apply sysctl params without reboot
    sudo sysctl --system
}


function setup_sudo_rsync {
    cat <<EOF | sudo tee /usr/local/bin/sudo_rsync
#!/bin/sh

exec sudo rsync \$@
EOF
    sudo chmod +x /usr/local/bin/sudo_rsync
}

function cluster_ip {
    if echo $1 | grep -E -o '^kb[0-9]$' > /dev/null; then
        # the name is kbX
        echo 192.168.1.22${1#"kb"}
    else
        # it's a labs device
        num=$(echo $1 | grep -o -E '[0-9]+')
        echo "192.168.1.22$(($num - 63))"
    fi
}

function configure_systemd_networkd {
    ip="$(cluster_ip $1)"
    # singular NIC at home
    cat <<EOF | sudo tee /etc/systemd/network/eth0.network
[Match]
Name=eth0

[Network]
Address=$ip/24
Gateway=192.168.1.1
DNS=192.168.1.1
EOF

    # management NIC on the big server, just bring it up
    cat <<EOF | sudo tee /etc/systemd/network/eno3.network
[Match]
Name=eno3

[Network]
DHCP=no
IPv6AcceptRA=no
EOF
    cat <<EOF | sudo tee /etc/systemd/network/breno3.network
[Match]
Name=breno3

[Network]
DHCP=ipv4
IPv6AcceptRA=no
EOF

    # cluster NIC on the big server
    cat <<EOF | sudo tee /etc/systemd/network/eno1.network
[Match]
Name=eno1

[Network]
Address=$ip/24
EOF

    sudo systemctl disable NetworkManager
    sudo systemctl mask NetworkManager
    sudo systemctl enable systemd-networkd
}


# basic system setup
if test -n "$1"; then
    sudo hostnamectl set-hostname $1
else
    echo "Skipping setting hostname, no new hostname provided in arg1"
fi


# disable swap
sudo dnf remove -y zram-generator-defaults
sudo touch /etc/systemd/zram-generator.conf
echo "zram" | sudo tee /etc/modprobe.d/blacklist
sudo systemctl mask dev-zram0.device


# useful utilities for interacting with the system
sudo dnf install -y htop nload fish micro iproute-tc python3-pip openvswitch openvswitch-devel rsync make ovn ovn-host ovn-vtep ovn-central ldns-utils bpftrace python3-bcc tcpdump scapy python3-psutil NetworkManager-ovs NetworkManager-tui

# packages for building OVS, could be usefull
INSTALL_PKGS=" \
    python3-pyyaml bind-utils procps-ng openssl numactl-libs firewalld-filesystem \
    libpcap hostname util-linux\
    libunwind-devel libatomic \
    python3-pyOpenSSL \
    autoconf automake libtool g++ gcc fedora-packager rpmdevtools \
    unbound unbound-devel groff python3-sphinx graphviz openssl openssl-devel \
    checkpolicy libcap-ng-devel selinux-policy-devel systemtap-sdt-devel libbpf-devel libxdp-devel numactl-devel \
    iptables iproute iputils hostname unbound-libs kmod go" && \
sudo dnf install --best --refresh -y --setopt=tsflags=nodocs $INSTALL_PKGS

# install helper for copying files to the system
setup_sudo_rsync

# install container runtime
install_docker

# install Kubernetes
install_kubernetes

# networking
configure_systemd_networkd $1

# Kubernetes networking
echo "KUBELET_EXTRA_ARGS=\"--node-ip=$(cluster_ip $1)\"" > /etc/sysconfig/kubelet
systemctl restart kubelet


# build OVN Kubernetes
cd $HOME
git clone https://github.com/ovn-org/ovn-kubernetes || true  # ignore failures, probably due to a repeated run
cd ovn-kubernetes
# make -C go-controller
# sudo make -C go-controller install


sudo reboot
