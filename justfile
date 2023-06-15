master_node := "kb1"
kb1_ip := "192.168.1.221"
kb2_ip := "192.168.1.222"
kb3_ip := "192.168.1.223"

# callback_url := "http://10.39.194.247:10001/"
callback_url := "https://dingo-10000.vsq.cz/"

# can be replaced with empty string, experiments will then not stop automatically and logs will be preserved
shell_exit := ""

set positional-arguments

deploy-analyzer nodes='.nodes.homelab':
    #!/bin/bash
    set -e

    . {{nodes}}
    
    pushd analyzer; cargo build --release --target=x86_64-unknown-linux-musl; popd
    
    poe --root cluster_tools run upload $NODE1 ../analyzer/target/x86_64-unknown-linux-musl/release/analyzer /usr/bin/analyzer
    poe --root cluster_tools run upload $NODE2 ../analyzer/target/x86_64-unknown-linux-musl/release/analyzer /usr/bin/analyzer
    poe --root cluster_tools run upload $NODE3 ../analyzer/target/x86_64-unknown-linux-musl/release/analyzer /usr/bin/analyzer
    poe --root cluster_tools run pod -m $NODE1 upload arch ../analyzer/target/x86_64-unknown-linux-musl/release/analyzer /usr/bin/analyzer
    poe --root cluster_tools run pod -m $NODE1 upload victim ../analyzer/target/x86_64-unknown-linux-musl/release/analyzer /usr/bin/analyzer
    poe --root cluster_tools run pod -m $NODE1 upload reflector ../analyzer/target/x86_64-unknown-linux-musl/release/analyzer /usr/bin/analyzer
    

setup: build && (setup-pods 'kb1') deploy-analyzer
    poe --root cluster_tools run provision 3

setup-pods root='kb1':
    poe --root cluster_tools run pod --master-node {{root}} deploy arch
    poe --root cluster_tools run pod --master-node {{root}} deploy reflector
    poe --root cluster_tools run pod --master-node {{root}} deploy netserver
    poe --root cluster_tools run pod --master-node {{root}} deploy victim

clean:
    poe --root cluster_tools run destroy --all

experiment-packet-fuzz nodes='.nodes.homelab': ( deploy-analyzer nodes ) && plot-last-packet-fuzz
    #!/bin/bash

    # load config variables
    . {{nodes}}
    
    # prepare global experiment ID
    experiment_id="packet_fuzz_$(date --iso-8601=minutes)"

    # start accepting test results
    pushd analyzer/results
    mkdir $experiment_id
    gimmedat --port 10000 --listen-ip 0.0.0.0 --secret irrelevant --public-access $experiment_id &
    echo "{{nodes}}" > "$experiment_id/nodes"
    popd

    # run experiment
    tmux new -d -s thesis-packet-fuzz \; split-window -h \;
    tmux send-keys -t thesis-packet-fuzz.1 "poe --root cluster_tools run pod -m $NODE1 ssh arch" ENTER
    tmux send-keys -t thesis-packet-fuzz.0 "poe --root cluster_tools run ssh $NODE2" ENTER
    sleep 4
    tmux send-keys -t thesis-packet-fuzz.1 "analyzer install-dependencies; sleep 10; analyzer --push-results-url {{callback_url}} packet-fuzz" ENTER
    tmux send-keys -t thesis-packet-fuzz.0 "sudo analyzer install-dependencies; sudo analyzer --push-results-url {{callback_url}} node-logger --only-upcalls" ENTER
    tmux attach -t thesis-packet-fuzz
    
    # stop accepting results
    kill %gimmedat

experiment-packet-flood count='20000' nodes='.nodes.homelab': ( deploy-analyzer nodes ) && plot-last-packet-flood link-last-packet-flood
    #!/bin/bash

    # load config variables
    . {{nodes}}
    
    # prepare global experiment ID
    experiment_id="packet_flood_$(date --iso-8601=minutes)"

    # start accepting test results
    pushd analyzer/results
    mkdir $experiment_id
    gimmedat --port 10000 --listen-ip 0.0.0.0 --secret irrelevant --public-access $experiment_id &
    echo "{{nodes}}" > $experiment_id/nodes
    popd

    # install dependencies
    poe --root cluster_tools run ssh $NODE2 -- sudo analyzer install-dependencies
    poe --root cluster_tools run pod -m $NODE1 ssh arch -- analyzer install-dependencies
    poe --root cluster_tools run pod -m $NODE1 ssh victim -- analyzer install-dependencies

    # run experiment
    tmux new -d -s thesis-packet-flood \; split-window -h \; split-window -v \;
    tmux send-keys -t thesis-packet-flood.0 "poe --root cluster_tools run ssh $NODE2 -- sh -c \"\\\"sudo analyzer --push-results-url {{callback_url}} node-logger --only-upcalls --runtime-sec 150\\\"\" ; {{shell_exit}}" ENTER
    tmux send-keys -t thesis-packet-flood.1 "poe --root cluster_tools run pod -m $NODE1 ssh victim -- sh -c \"\\\"analyzer --push-results-url {{callback_url}} victim --runtime-sec 150\\\"\" ; {{shell_exit}}" ENTER
    tmux send-keys -t thesis-packet-flood.2 "poe --root cluster_tools run pod -m $NODE1 ssh arch -- sh -c \"\\\"sleep 10; analyzer --push-results-url {{callback_url}} packet-flood --count {{count}} --runtime-sec 120\\\"\" ; {{shell_exit}}" ENTER
    
    tmux attach -t thesis-packet-flood
    
    # stop accepting results
    kill %gimmedat
    
plot-last-packet-fuzz:
    cd analyzer; QT_QPA_PLATFORM=xcb python postprocessing/packet_fuzzing.py $(ls -d results/packet_fuzz_* | sort | tail -n 1)


plot-last-packet-flood:
    cd analyzer; QT_QPA_PLATFORM=xcb python postprocessing/packet_flood.py $(ls -d results/packet_flood_2023* | sort | tail -n 1)


@poe *args:
    poe --root cluster_tools run {{args}}

pod *args:
    poe --root cluster_tools run pod {{args}}

plot type file:
    #!/bin/bash
    case "{{type}}" in
        randomized_eviction_timeout)
            QT_QPA_PLATFORM=xcb python analyzer/postprocessing/randomized_eviction_timeout.py {{file}}
            ;;
        *fuzz*)
            QT_QPA_PLATFORM=xcb python analyzer/postprocessing/packet_fuzzing.py {{file}}
            ;;
        *flood*)
            QT_QPA_PLATFORM=xcb python analyzer/postprocessing/packet_flood.py {{file}}
            ;;
        *)
            echo "Unknown plot type $type"
            ;;
    esac

ssh where:
    poe --root cluster_tools run ssh {{where}}


build:
    #!/bin/bash

    cd analyzer
    cargo build --release --target=x86_64-unknown-linux-musl
    podman build -t registry.homelab.vsq.cz/analyzer .
    podman push registry.homelab.vsq.cz/analyzer


localize-containers:
    podman pull docker.io/archlinux:latest
    podman tag docker.io/archlinux:latest registry.homelab.vsq.cz/archlinux:latest
    podman push registry.homelab.vsq.cz/archlinux:latest

    podman pull ghcr.io/ovn-org/ovn-kubernetes/ovn-kube-f:master
    podman tag ghcr.io/ovn-org/ovn-kubernetes/ovn-kube-f:master registry.homelab.vsq.cz/ovn-kube-f:master
    podman push registry.homelab.vsq.cz/ovn-kube-f:master


prep-builder:
    podman build -t ovn-builder .

prep-ovs full="true":
    #!/bin/bash
    set -e
    cd ovs
    pod="podman run --rm -ti -v $PWD:/root/ovs -w /root/ovs ovn-builder"
    
    if {{full}}; then
        $pod make distclean || true
        $pod ./boot.sh
        $pod ./configure --prefix=/usr --libdir=/usr/lib64 --enable-usdt-probes CFLAGS="-ggdb3 -O2 -fno-omit-frame-pointer -msse2"
    fi
    $pod make -j $(nproc)

deploy-custom-ovs: (prep-ovs "false")
    #!/bin/bash
    set -e
    poe --root cluster_tools run upload-everywhere ../ovs /root/
    poe --root cluster_tools run ssh kb1 -- sudo make -C /root/ovs install
    poe --root cluster_tools run ssh kb1 -- sudo systemctl restart openvswitch
    poe --root cluster_tools run ssh kb2 -- sudo make -C /root/ovs install
    poe --root cluster_tools run ssh kb2 -- sudo systemctl restart openvswitch
    poe --root cluster_tools run ssh kb3 -- sudo make -C /root/ovs install
    poe --root cluster_tools run ssh kb3 -- sudo systemctl restart openvswitch
    

prep-ovn full="true":
    #!/bin/bash
    set -e
    cd ovn
    pod="podman run --rm -ti -v $PWD:/root/ovn -v $PWD/../ovs:/root/ovs -w /root/ovn ovn-builder"
    if {{full}}; then
        $pod make clean || true
        $pod ./boot.sh
        $pod ./configure --with-ovs-source=../ovs/ --prefix=/usr --libdir=/usr/lib64
    fi
    $pod make -j $(nproc)

prep-ovn-kubernetes:
    make -C ovn-kubernetes/go-controller
    find ovn-kubernetes/go-controller/_output/go/bin/ -maxdepth 1 -type f -exec cp -f {} ovn-kubernetes/dist/images/ \;
    

build-debug-ovn-kube full="false": prep-builder (prep-ovs full) (prep-ovn full) (prep-ovn-kubernetes)
    #mkdir -p build_root
    #make -C ovs DESTDIR=$PWD/build_root install
    #make -C ovn DESTDIR=$PWD/build_root install
    
    podman build -t registry.homelab.vsq.cz/ovn-kube-f:latest -f cluster_tools/install-scripts/Dockerfile.fedora.dev .
    podman push registry.homelab.vsq.cz/ovn-kube-f:latest

reload-ovn node="kb2": build
    poe --root cluster_tools run ssh {{node}} -- sudo analyzer reload-ovn


link-last-packet-flood:
    ln -srfT $(ls -d analyzer/results/packet_flood_2023* | sort | tail -n 1) analyzer/results/packet_flood_last

test-kb2-tracing:
    poe --root cluster_tools run ssh kb2 -- sudo bpftrace -p \$\(pgrep ovs-vswitchd\) -e \'usdt:/proc/\'\$\(pgrep ovs-vswitchd\)\'/root/usr/sbin/ovs-vswitchd:udpif_revalidator:new_flow_limit \{ printf\(\"new flow limit: %lld\\n\", arg0\)\; \}\'


text:
    make -C text

show-text:
    evince text/thesis.pdf &
