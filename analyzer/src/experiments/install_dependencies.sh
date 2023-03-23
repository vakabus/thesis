#!/bin/bash

DEPS_FEDORA="python3-psutil scapy tcpdump"
DEPS_ARCH="python-psutil scapy tcpdump"

if command -v pacman; then
    pacman -Sy --noconfirm $DEPS_ARCH
elif command -v dnf; then
    dnf install -y $DEPS_FEDORA
else
    echo "Unknown package manager"
    exit 1
fi
