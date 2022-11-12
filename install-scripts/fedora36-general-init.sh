#!/bin/bash

set -e
export PATH=/usr/local/bin:/usr/bin:/usr/local/sbin:/usr/sbin

# wait for full startup
echo "Waiting for full system startup..."
while [[ "$(systemctl show --property=SystemState)" != "SystemState=running" ]]; do
    sleep 1
done


sudo hostnamectl set-hostname $1
sudo dnf remove -y zram-generator-defaults
sudo dnf install -y htop nload fish micro iproute-tc python3-pip openvswitch openvswitch-devel rsync make ovn ovn-host ovn-vtep ovn-central ldns-utils

sudo dnf -y install dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo dnf install -y https://github.com/Mirantis/cri-dockerd/releases/download/v0.2.6/cri-dockerd-0.2.6-3.fc36.x86_64.rpm

sudo systemctl enable --now docker
sudo systemctl enable --now cri-docker


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

# remove systemd-resolved before reboot
sudo dnf remove -y systemd-resolved
sudo rm -f /etc/resolv.conf

sudo reboot