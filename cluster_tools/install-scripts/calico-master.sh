#!/bin/bash

# init cluster
sudo kubeadm init --pod-network-cidr=10.244.0.0/16 --cri-socket=unix:///var/run/cri-dockerd.sock
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

# wait til its ready
kubectl get pods -A

# deploy calico
kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/v3.24.3/manifests/tigera-operator.yaml
curl https://raw.githubusercontent.com/projectcalico/calico/v3.24.3/manifests/custom-resources.yaml -O
micro custom-resources.yaml  # edit CIDR to match cluster init
kubectl create -f custom-resources.yaml 

# enjoy
watch kubectl get pods -A
