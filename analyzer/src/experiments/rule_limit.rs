fn setup_crazy_pinger(pinger: &Pinger, n: usize) {
    for i in 0..n {
        let addr = Ipv4Addr::new(10, 66, ((i >> 8) & 0xFF) as u8, (i & 0xFF) as u8);
        pinger.add_ipaddr(&addr.to_string());
    }
}

fn stupid_number_of_pings_measurement(args: &Args, n: usize) -> Vec<Duration> {
    let (pinger, receiver) = create_pinger();


    setup_crazy_pinger(&pinger, n); // add dummy targets
    pinger.add_ipaddr(&args.target_ip); // add real target
    let target = Ipv4Addr::from_str(&args.target_ip).unwrap();

    const WARMUP_ROUNDS: usize = 5;
    const READ_ROUND: usize = 20;
    let mut rounds = 0;
    let mut results = Vec::with_capacity(READ_ROUND);

    pinger.run_pinger();
    loop {
        match receiver.recv() {
            Ok(result) => match result {
                Idle { addr } => {
                    // don't care
                }
                Receive { addr, rtt } => {
                    if addr == target {
                        if rounds > WARMUP_ROUNDS {
                            results.push(rtt);
                        }
                        rounds += 1;
                    }
                }
            },
            Err(_) => panic!("Worker thread did something weird!"),
        };

        if rounds > WARMUP_ROUNDS + READ_ROUND {
            break;
        }
    }

    pinger.stop_pinger();

    results
}

fn measure_concurrent_connections_latency(args: Args) -> Vec<(usize, Vec<Duration>)> {
    let mut samples = Vec::new();

    for i in 0..20 {
        let mut r = stupid_number_of_pings_measurement(&args, i * 100);
        samples.push((i * 100, r.clone()));

        // print fancy message
        r.sort();
        let avg: Duration = r.iter().skip(1).take(r.len() - 2).sum::<Duration>() / ((r.len() - 2) as u32);
        info!("{} concurrent pings -> target avg latency {:?}", i * 100, avg);

        sleep(Duration::from_millis(args.gap));
    }

    samples
}