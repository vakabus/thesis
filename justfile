set positional-arguments

experiment-packet-fuzz host_node pod_ip:
	cd analyzer; cargo build --release
	poe --root cluster_tools run upload-everywhere ../analyzer/target/release/analyzer /usr/bin/analyzer
	poe --root cluster_tools run upload-arch kb1 ../analyzer/target/release/analyzer /usr/bin/analyzer
	tmux new -d -s thesis-packet-fuzz \; split-window -h \;
	tmux send-keys -t thesis-packet-fuzz.1 "poe --root cluster_tools run shell-arch kb1" ENTER
	tmux send-keys -t thesis-packet-fuzz.0 "poe --root cluster_tools run ssh {{host_node}}" ENTER
	sleep 2
	tmux send-keys -t thesis-packet-fuzz.1 "analyzer packet-fuzz" ENTER
	tmux send-keys -t thesis-packet-fuzz.0 "sudo analyzer log-flow-stats --log-ip {{pod_ip}}" ENTER
	tmux attach -t thesis-packet-fuzz
	echo "Downloading experiment results"
	poe --root cluster_tools run fetch-arch kb1 ../analyzer/results
	cd analyzer; QT_QPA_PLATFORM=xcb python postprocessing/packet_fuzzing.py results/fetch/$(ls results/fetch/ | tail -n 1)

@poe *args:
	poe --root cluster_tools run {{args}}


