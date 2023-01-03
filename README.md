# Performance of Open vSwitch-based Kubernetes Cluster in Pathological Cases# 

Modern containerized cloud computing systems have complex requirements for their networking backends. Demand for features like seamless cross-data-center networking, multi-tenancy and security policies necessitated use of the Software Defined Networking (SDN) concept and, by the nature of containerized systems, extensive use of virtualized networks.

The current shift to microservices and the resulting increase of endpoints and need of rapid reconfiguration put emphasis on the SDN control plane performance and scalability.

A commonly deployed solution is Kubernetes for container orchestration and Open vSwitch for the virtualized SDN, used either directly or indirectly. However, it remains a question how well these solutions are adapted to the networking needs of microservices.

The goal of this work is exploring the performance and scalability of common Kubernetes and Open vSwitch configurations with the focus on pathological cases. It should explore how network performance characteristics are influenced by external factors, such as pathologic traffic patterns or pathologic microservices networking behavior. It should seek performance and scalability bottlenecks, evaluate whether and how they are relevant to the cluster security and propose optimization.


_The thesis supervisor is @jbenc_

## What is in this repository?

- `cluster_tools/` - tools for automated installation of Kubernetes and helpers for setting up experiments
- `analyzer/` - experiments and related data processing

See the respective directories for information about their content.
