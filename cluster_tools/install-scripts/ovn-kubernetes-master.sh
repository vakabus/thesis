#!/bin/bash
set -e

# init Kubernetes cluster
sudo kubeadm init --pod-network-cidr=10.244.0.0/16 --service-cidr=10.245.0.0/16 --skip-phases=addon/kube-proxy --cri-socket=unix:///var/run/cri-dockerd.sock
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

# deploy OVN Kubernetes
pushd $HOME/ovn-kubernetes/dist/images
./daemonset.sh --image=ghcr.io/ovn-org/ovn-kubernetes/ovn-kube-f:master --net-cidr=10.244.0.0/16 --svc-cidr=10.245.0.0/16 --gateway-mode="local" --k8s-apiserver=https://$(hostname -I | cut -f1 -d' '):6443
popd
kubectl create -f $HOME/ovn-kubernetes/dist/yaml/ovn-setup.yaml
kubectl create -f $HOME/ovn-kubernetes/dist/yaml/ovs-node.yaml
kubectl create -f $HOME/ovn-kubernetes/dist/yaml/ovnkube-db.yaml
kubectl create -f $HOME/ovn-kubernetes/dist/yaml/ovnkube-node.yaml
kubectl create -f $HOME/ovn-kubernetes/dist/yaml/ovnkube-master.yaml

