# Analyser

A tool for running experiments on Kubernetes cluster targeting OVS, part of a Master's thesis. Details about the experiments can be found in the thesis.

## Usage

Use the `--help` option to print the help message:

```
Usage: analyzer [OPTIONS] <COMMAND>

Commands:
  randomized-eviction-timeout  Randomized measurement of flow eviction timeout
  node-logger                  Collect statistics about OVS on a cluster node
  packet-fuzz                  Packet fuzzing tool
  log-flow-ops                 Debugging tool for testing eBPF tracing
  install-dependencies         Install dependencies on the distro
  packet-flood                 Fill flow table with given number of rules
  reflector                    Ethernet echo server
  victim                       Latency measurement tool intended to be run in a pod on a stressed host
  reload-ovn                   Reload ovn-kubernetes on cluster node
  help                         Print this message or the help of the given subcommand(s)

Options:
      --push-results-url <PUSH_RESULTS_URL>  
  -h, --help                                 Print help information
  -V, --version                              Print version information
```

Special mention is worth to the `--push-results-url` option. When supplied with the URL, the `analyzer` invokes the command `curl -T result.csv {URL}` for every file with results it creates. This works especially well when used together with the [`gimmedat`](https://github.com/vakabus/gimmedat) project to run the collector server.

## Processing results

