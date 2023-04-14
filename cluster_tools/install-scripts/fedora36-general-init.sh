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
    sudo dnf install -y https://github.com/Mirantis/cri-dockerd/releases/download/v0.3.0/cri-dockerd-0.3.0-3.fc36.x86_64.rpm

    sudo systemctl enable --now docker
    sudo systemctl enable --now cri-docker
}

function install_containerd {
    # does not work, but leaving it here for potential future use

    # install runc
    wget https://github.com/opencontainers/runc/releases/download/v1.1.4/runc.amd64
    sudo install -m 755 runc.amd64 /usr/local/sbin/runc

    # install containerd
    wget https://github.com/containerd/containerd/releases/download/v1.6.14/containerd-1.6.14-linux-amd64.tar.gz
    sudo tar Czxvf /usr/local containerd-1.6.14-linux-amd64.tar.gz

    wget https://raw.githubusercontent.com/containerd/containerd/main/containerd.service
    sudo mv containerd.service /usr/lib/systemd/system/
    sudo restorecon -Rv /usr/lib/systemd/system/

    sudo mkdir -p /etc/containerd/
    containerd config default | sudo tee /etc/containerd/config.toml
    sudo sed -i 's/SystemdCgroup \= false/SystemdCgroup \= true/g' /etc/containerd/config.toml

    sudo systemctl daemon-reload
    sudo systemctl enable --now containerd
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



function configure_systemd_networkd {
    ip=22${1#"kb"}
    cat <<EOF | sudo tee /etc/systemd/network/breth0.network
[Match]
Name=eth0

[Network]
Address=192.168.1.$ip/24
Gateway=192.168.1.1
DNS=192.168.1.1
EOF

    sudo systemctl disable NetworkManager
    sudo systemctl mask NetworkManager
    sudo systemctl enable systemd-networkd
}






# basic system setup
sudo hostnamectl set-hostname $1

sudo dnf remove -y zram-generator-defaults
sudo touch /etc/systemd/zram-generator.conf
echo "zram" | sudo tee /etc/modprobe.d/blacklist
sudo systemctl mask dev-zram0.device

sudo dnf install -y htop nload fish micro iproute-tc python3-pip openvswitch openvswitch-devel rsync make ovn ovn-host ovn-vtep ovn-central ldns-utils

# install helper for copying files to the system
setup_sudo_rsync

# we currently have a working networking, however DHCP will not renew
# this however does not work as intended
configure_systemd_networkd $1
#
# remove systemd-resolved before reboot
# sudo dnf remove -y systemd-resolved
# sudo rm -f /etc/resolv.conf
echo "DNS=192.168.1.1" | sudo tee -a /etc/systemd/resolved.conf


# install container runtime
install_docker

# install Kubernetes
install_kubernetes

# install tools used for debugging
sudo dnf install -y python3-bcc tcpdump scapy python3-psutil


# schedule reboot and successfully exit
echo "Will reboot shortly..."