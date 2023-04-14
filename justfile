master_node := "kb1"
kb1_ip := "192.168.1.221"
kb2_ip := "192.168.1.222"
kb3_ip := "192.168.1.223"

set positional-arguments

deploy-analyzer:
	cd analyzer; cargo build --release --target=x86_64-unknown-linux-musl
	poe --root cluster_tools run upload-everywhere ../analyzer/target/x86_64-unknown-linux-musl/release/analyzer /usr/bin/analyzer
	poe --root cluster_tools run pod upload arch ../analyzer/target/x86_64-unknown-linux-musl/release/analyzer /usr/bin/analyzer
	poe --root cluster_tools run pod upload victim ../analyzer/target/x86_64-unknown-linux-musl/release/analyzer /usr/bin/analyzer
	poe --root cluster_tools run pod upload reflector ../analyzer/target/x86_64-unknown-linux-musl/release/analyzer /usr/bin/analyzer
	

setup: build && deploy-analyzer
	poe --root cluster_tools run provision 3
	poe --root cluster_tools run pod deploy arch
	poe --root cluster_tools run pod deploy reflector
	poe --root cluster_tools run pod deploy netserver
	poe --root cluster_tools run pod deploy victim

clean:
	poe --root cluster_tools run destroy --all

experiment-packet-fuzz host_node pod_ip: deploy-analyzer && plot-last-packet-fuzz
	#!/bin/bash
	
	# upload binaries
	poe --root cluster_tools run pod upload arch ../analyzer/target/release/analyzer /usr/bin/analyzer

	# prepare global experiment ID
	experiment_id="packet_fuzz_$(date --iso-8601=minutes)"

	# start accepting test results
	cd analyzer/results
	mkdir $experiment_id
	gimmedat --port 3333 --listen-ip 0.0.0.0 --secret irrelevant --public-access $experiment_id &
	cd ../..

	# run experiment
	tmux new -d -s thesis-packet-fuzz \; split-window -h \;
	tmux send-keys -t thesis-packet-fuzz.1 "poe --root cluster_tools run pod ssh arch" ENTER
	tmux send-keys -t thesis-packet-fuzz.0 "poe --root cluster_tools run ssh kb2" ENTER
	sleep 4
	tmux send-keys -t thesis-packet-fuzz.1 "analyzer install-dependencies; analyzer --push-results-url http://dingo.lan:3333/ packet-fuzz" ENTER
	tmux send-keys -t thesis-packet-fuzz.0 "sudo analyzer install-dependencies; sudo analyzer --push-results-url http://dingo.lan:3333/ log-flow-stats --log-ip {{pod_ip}}" ENTER
	tmux attach -t thesis-packet-fuzz
	
	# stop accepting results
	kill %gimmedat

experiment-packet-flood: deploy-analyzer && plot-last-packet-flood
	#!/bin/bash
	
	# upload binaries to pods
	poe --root cluster_tools run pod upload arch ../analyzer/target/x86_64-unknown-linux-musl/release/analyzer /usr/bin/analyzer
	poe --root cluster_tools run pod upload victim ../analyzer/target/x86_64-unknown-linux-musl/release/analyzer /usr/bin/analyzer

	# prepare global experiment ID
	experiment_id="packet_flood_$(date --iso-8601=minutes)"

	# start accepting test results
	cd analyzer/results
	mkdir $experiment_id
	gimmedat --port 3333 --listen-ip 0.0.0.0 --secret irrelevant --public-access $experiment_id &
	cd ../..

	# run experiment
	tmux new -d -s thesis-packet-flood \; split-window -h \; split-window -v \;
	tmux send-keys -t thesis-packet-flood.0 "poe --root cluster_tools run ssh kb2" ENTER
	tmux send-keys -t thesis-packet-flood.1 "poe --root cluster_tools run pod ssh victim" ENTER
	tmux send-keys -t thesis-packet-flood.2 "poe --root cluster_tools run pod ssh arch" ENTER
	sleep 4
	tmux send-keys -t thesis-packet-flood.0 "sudo analyzer install-dependencies; sudo analyzer --push-results-url http://dingo.lan:3333/ node-logger --only-upcalls" ENTER
	tmux send-keys -t thesis-packet-flood.1 "analyzer install-dependencies; analyzer --push-results-url http://dingo.lan:3333/ victim" ENTER
	tmux send-keys -t thesis-packet-flood.2 "analyzer install-dependencies; sleep 10; analyzer --push-results-url http://dingo.lan:3333/ packet-flood --count 20000" ENTER
	tmux attach -t thesis-packet-flood
	
	# stop accepting results
	kill %gimmedat
	
plot-last-packet-fuzz:
	cd analyzer; QT_QPA_PLATFORM=xcb python postprocessing/packet_fuzzing.py $(ls -d results/packet_fuzz_* | sort | tail -n 1)


plot-last-packet-flood:
	cd analyzer; QT_QPA_PLATFORM=xcb python postprocessing/packet_flood.py $(ls -d results/packet_flood_* | sort | tail -n 1)


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
