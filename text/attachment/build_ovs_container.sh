#!/bin/bash

set -e

CONTAINER_NAME=ovn-kube-f:latest

git clone https://github.com/ovn-org/ovn-kubernetes.git # our HEAD was 5283e006f88f140d5053c959915da56ebc4fff76
git clone https://github.com/ovn-org/ovn.git # our HEAD was 12693ddecbf33044136fa392381694218dd08646
git clone https://github.com/openvswitch/ovs.git --branch branch-3.1  # our HEAD was 771c989a9a957b2e487c9312eaee3bfb87638be5

# add USDT probes to OVS
pushd ovs
git am ../ovs-usdt-probes.patch
popd

# build helper container for compilation
podman build -t ovn-builder -f Dockerfile.builder .

# build OVS
(
    cd ovs
    pod="podman run --rm -ti -v $PWD:/root/ovs -w /root/ovs ovn-builder"
        
    $pod make distclean || true
    $pod ./boot.sh
    $pod ./configure --prefix=/usr --libdir=/usr/lib64 --enable-usdt-probes CFLAGS="-ggdb3 -O2 -fno-omit-frame-pointer -msse2"
    $pod make -j $(nproc)
)

# build OVN
(
    cd ovn
    pod="podman run --rm -ti -v $PWD:/root/ovn -v $PWD/../ovs:/root/ovs -w /root/ovn ovn-builder"
    $pod make clean || true
    $pod ./boot.sh
    $pod ./configure --with-ovs-source=../ovs/ --prefix=/usr --libdir=/usr/lib64
    $pod make -j $(nproc)
)

# build OVN-Kubernetes
(
    make -C ovn-kubernetes/go-controller
    find ovn-kubernetes/go-controller/_output/go/bin/ -maxdepth 1 -type f -exec cp -f {} ovn-kubernetes/dist/images/ \;        
)

# build the actual container
podman build -t $CONTAINER_NAME -f Dockerfile.ovs-node .
