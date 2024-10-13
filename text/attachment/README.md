# How to replicate our results

1. prepare OVS container
2. setup a Kubernetes cluster
3. deploy experimental pods
4. run experiments
5. collect and process results

## OVS container preparation

See appendix A in the thesis text for details...

First, prepare a OCI image registry. We'll use `$registry` for its resolvable domain.

```sh
# install dependencies: podman, git, go toolchain
bash build_ovs_container.sh
podman tag ovn-kube-f:latest $registry/ovn-kube-f:latest
podman push $registry/ovn-kube-f:latest
```

## Cluster setup

See appendix B in the thesis text for details...

1. setup 3 Fedora 38 systems
2. modify `setup1-general.sh` to match your networking setup
3. run `setup1-general.sh $hostname` on all of them, where `$hostname` is one of `kb1`, `kb2` or `kb3`
4. edit the `setup2-master.sh` to match your OVS container name
5. run `setup2-master.sh` on `kb1`
6. run `kubeadm token create --print-join-command` on `kb1` and copy the result
7. append `--cri-socket=unix:///var/run/cri-dockerd.sock` to the command from previous step and run it on `kb2` and `kb3`

## Deploy pods

Also described in appendix B in the thesis text...

1. build the `analyzer` (see appendix C for details) by calling `cargo build --release --target=x86_64-unknown-linux-musl` in the `analyzer` directory
2. build the `analyzer` container and push it to the registry `cd analyzer; podman build -t $registry/analyzer:latest .; podman push $registry/analyzer:latest`
3. copy the directory `kube_configs` to `kb1`
4. edit the `kube_configs/reflector.yaml` file so that it refers to `$registry/analyzer:latest`
3. run `for f in kube_configs/*; do kubectl create -f $f; done` on `kb1`

## Run experiments

1. copy the `analyzer/target/x86_64-unknown-linux-musl/release/analyzer` binary to `kb2` and the `arch` pod
2. run one of the experiments (which commands have to be run where is documented in appendix C section 2)
3. collect all generated files by all the `analyzer` command invocations to a single directory (`$results_dir`)

## Process the experiments

The `analyzer/postprocessing` directory contains results processing scripts. The processing into plots could look like this:

```sh
# the eviction timeout experiment
python analyzer/postprocessing/randomized_eviction_timeout.py $results_dir/*.csv randomized_eviction_timeout.png

# packet flood results
python analyzer/postprocessing/packet_flood_basic.py $results_dir packet_flood_bare_15k.png
python analyzer/postprocessing/packet_flood_basic.py $results_dir packet_flood_bare_50k.png
python analyzer/postprocessing/packet_flood.py $results_dir packet_flood_limited_resources_50k.png
python analyzer/postprocessing/packet_flood_latency.py $results_dir packet_flood_50k_latency.png

# packet fuzzing
python analyzer/postprocessing/packet_fuzzing.py $results_dir packet_fuzz.png
```


