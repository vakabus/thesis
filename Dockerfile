#
# This Dockerfile builds the development image of Kubernetes OVN CNI networking
# stack. It provides the OVN-Kubernetes CNI plugin (OVN-Kubernetes) and all the
# required binaries from OVN and OVS. By default OVN and OVS binaries are built
# using the master branch of the respective projects.
#
# NOTE:
# 1) Binaries are built using the version specified using OVN-BRANCH,
# OVS-BRANCH args below in the Dockerfile. By default the branch is set to
# master, so it will build OVN and OVS binaries from the master branch code.
# Please change the branch name if image needs to be build with different
# branch.
#
# 2) This image is only for development environment, so please DO NOT DEPLOY
# this image in any production environment.
#

FROM fedora:38 AS ovnbuilder

USER root

ENV PYTHONDONTWRITEBYTECODE yes

# Install tools that are required for building ovs/ovn.
RUN INSTALL_PKGS=" \
    python3-pyyaml bind-utils procps-ng openssl numactl-libs firewalld-filesystem \
    libpcap hostname util-linux\
    libunwind-devel libatomic \
    python3-pyOpenSSL \
    autoconf automake libtool g++ gcc fedora-packager rpmdevtools \
    unbound unbound-devel groff python3-sphinx graphviz openssl openssl-devel \
    checkpolicy libcap-ng-devel selinux-policy-devel systemtap-sdt-devel libbpf-devel libxdp-devel numactl-devel \
    iptables iproute iputils hostname unbound-libs kubernetes-client kmod" && \
    dnf install --best --refresh -y --setopt=tsflags=nodocs $INSTALL_PKGS && \
    dnf clean all && rm -rf /var/cache/dnf/*

WORKDIR /root
