# Cluster tools

Goals:
* automatically and reproducibly install Kubernetes clusters with OVN-Kubernetes networking (as Proxmox VMs)
* provide helpers for interactions with the cluster


## How to use

```sh
poetry install
poe run  # will show help
```

Warning, the source code contains several hard-coded assumptions about the underlying infrastructure. The code will likely fail whenever you try to run it outside of my home network/VPN.