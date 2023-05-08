#!/bin/bash

DEPS_FEDORA="python3-psutil scapy tcpdump perf bpftrace bcc"
DEPS_ARCH="python-psutil scapy tcpdump perf bpftrace"

if command -v pacman; then
    pacman -Sy --noconfirm $DEPS_ARCH
elif command -v dnf; then
    dnf install -y $DEPS_FEDORA
else
    echo "Unknown package manager"
    exit 1
fi
