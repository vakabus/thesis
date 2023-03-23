set positional-arguments

deploy-analyzer:
	cd analyzer; cargo build --release
	poe --root cluster_tools run upload-everywhere ../analyzer/target/release/analyzer /usr/bin/analyzer

experiment-packet-fuzz host_node pod_ip: deploy-analyzer && plot-last-packet-fuzz
	#!/bin/bash
	
	# upload binaries
	poe --root cluster_tools run upload-arch kb1 ../analyzer/target/release/analyzer /usr/bin/analyzer

	# prepare global experiment ID
	experiment_id="packet_fuzz_$(date --iso-8601=minutes)"

	# start accepting test results
	cd analyzer/results
	mkdir $experiment_id
	gimmedat --port 3333 --listen-ip 0.0.0.0 --secret irrelevant --public-access $experiment_id &
	cd ../..

	# run experiment
	tmux new -d -s thesis-packet-fuzz \; split-window -h \;
	tmux send-keys -t thesis-packet-fuzz.1 "poe --root cluster_tools run shell-arch kb1" ENTER
	tmux send-keys -t thesis-packet-fuzz.0 "poe --root cluster_tools run ssh {{host_node}}" ENTER
	sleep 4
	tmux send-keys -t thesis-packet-fuzz.1 "analyzer install-dependencies; analyzer --push-results-url http://dingo.lan:3333/ packet-fuzz" ENTER
	tmux send-keys -t thesis-packet-fuzz.0 "sudo analyzer install-dependencies; sudo analyzer --push-results-url http://dingo.lan:3333/ log-flow-stats --log-ip {{pod_ip}}" ENTER
	tmux attach -t thesis-packet-fuzz
	
	# stop accepting results
	kill %gimmedat
	

plot-last-packet-fuzz:
	cd analyzer; QT_QPA_PLATFORM=xcb python postprocessing/packet_fuzzing.py $(ls -d results/packet_fuzz_* | sort | tail -n 1)


@poe *args:
	poe --root cluster_tools run {{args}}

plot type file:
	#!/bin/bash
	case "{{type}}" in
		randomized_eviction_timeout)
			QT_QPA_PLATFORM=xcb python analyzer/postprocessing/randomized_eviction_timeout.py {{file}}
			;;
		*fuzz*)
			QT_QPA_PLATFORM=xcb python analyzer/postprocessing/packet_fuzzing.py {{file}}
			;;
		*)
			echo "Unknown plot type $type"
			;;
	esac

ssh where:
	poe --root cluster_tools run ssh {{where}}
