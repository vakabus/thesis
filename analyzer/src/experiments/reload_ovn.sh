#!/bin/bash

set -exo pipefail

# pull new image
docker pull registry.homelab.vsq.cz/ovn-kube-f:latest

# force Kubernetes to restart the container
killall ovs-vswitchd
#docker ps | grep k8s_ovs-daemons_ovs-node | cut -f1 -d' ' | xargs docker stop


# wait for restart
#while ! docker ps | grep k8s_ovs-daemons_ovs-node; do
#    echo "waiting for a new ovs-node container"
#    sleep 3
#done


# give it a bit more
sleep 60
# and restart it manually
docker ps | grep k8s_ovs-daemons_ovs-node | cut -f1 -d' ' | xargs docker restart



# force restart other containers
#sudo docker ps | grep k8s_arch | cut -f1 -d' ' | xargs sudo docker stop