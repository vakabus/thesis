#!/bin/bash
set -e

IMAGE=registry.homelab.vsq.cz/ovn-kube-f:latest

# wait for full startup
echo "Waiting for full system startup..."
while [[ "$(systemctl show --property=SystemState)" != "SystemState=running" ]]; do
    sleep 1
done

# init Kubernetes cluster
sudo kubeadm init --pod-network-cidr=10.244.0.0/16 --service-cidr=10.245.0.0/16 --skip-phases=addon/kube-proxy --cri-socket=unix:///var/run/cri-dockerd.sock --apiserver-advertise-address=192.168.1.221
mkdir -p $HOME/.kube
sudo cp /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

# deploy OVN Kubernetes
pushd $HOME/ovn-kubernetes/dist/images
./daemonset.sh --image=$IMAGE --net-cidr=10.244.0.0/16 --svc-cidr=10.245.0.0/16 --gateway-mode="local" --k8s-apiserver=https://192.168.1.221:6443
popd
kubectl create -f $HOME/ovn-kubernetes/dist/yaml/ovn-setup.yaml
kubectl create -f $HOME/ovn-kubernetes/dist/yaml/ovs-node.yaml
kubectl create -f $HOME/ovn-kubernetes/dist/yaml/ovnkube-db.yaml
kubectl create -f $HOME/ovn-kubernetes/dist/yaml/ovnkube-node.yaml
kubectl create -f $HOME/ovn-kubernetes/dist/yaml/ovnkube-master.yaml


# to change the resource limits of OVS on a running cluster
#   1. edit $HOME/ovn-kubernetes/dist/yaml/ovs-node.yaml
#   2. kubectl apply -f $HOME/ovn-kubernetes/dist/yaml/ovs-node.yaml
#   3. wait 3 minutes for the cluster to settle into a stable state
