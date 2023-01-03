use std::time::Instant;

use anyhow::Context;
use serde::Serialize;
use subprocess::{Exec, Redirection};

#[derive(Debug, Serialize)]
pub struct OVSStats {
    pub ms_since_start: u64,

    pub lookup_hit: usize,
    pub lookup_missed: usize,
    pub lookup_lost: usize,
    pub flows: usize,
    pub masks_hit: usize,
    pub masks_total: usize,
    pub masks_hit_per_pkt: f32,
    pub cache_hit: usize,
    pub cache_hit_rate: f32,
    pub cache_masks_size: usize,
}

fn geteuid() -> u32 {
    unsafe { libc::geteuid() as u32 }
}

pub fn get_ovs_dpctl_show(program_start: Instant) -> Result<OVSStats, anyhow::Error> {
    if geteuid() != 0 {
        panic!("trying to call `ovs-dpctl show` without root privileges");
    }

    let child = Exec::cmd("ovs-dpctl")
        .arg("show")
        .stdout(Redirection::Pipe)
        .capture()?;

    let out = child.stdout_str();
    let lines = out.lines();

    // example output that we are parsing:
    //
    // $ ovs-dpctl show
    // system@ovs-system:
    //   lookups: hit:34085 missed:4207 lost:0
    //   flows: 3
    //   masks: hit:83064 total:3 hit/pkt:2.17
    //   cache: hit:27209 hit-rate:71.06%
    //   caches:
    //     masks-cache: size:256
    // port 0: ovs-system (internal)
    // port 1: br-int (internal)
    // port 2: genev_sys_6081 (geneve: packet_type=ptap)
    // port 3: ovn-k8s-mp0 (internal)
    // port 4: eth0
    // port 5: breth0 (internal)

    // interface name
    let mut lines = lines.skip(1);

    // lookups
    let mut lookups = lines
        .next()
        .context("parsing step 1")?
        .trim_start()
        .split(' ')
        .skip(1);
    let lookup_hit: usize = lookups
        .next()
        .context("parsing step 2")?
        .split(':')
        .nth(1)
        .context("parsing step 3")?
        .parse()
        .context("parsing step 4")?;
    let lookup_missed: usize = lookups
        .next()
        .context("parsing step 5")?
        .split(':')
        .nth(1)
        .context("parsing step 6")?
        .parse()
        .context("parsing step 7")?;
    let lookup_lost: usize = lookups
        .next()
        .context("parsing step 8")?
        .split(':')
        .nth(1)
        .context("parsing step 9")?
        .parse()
        .context("parsing step 10")?;

    // flows
    let flows: usize = lines
        .next()
        .context("parsing step 11")?
        .split(' ')
        .rev()
        .next()
        .context("parsing step 12")?
        .parse()
        .context("parsing step 13")?;

    // masks
    let mut masks = lines
        .next()
        .context("parsing step 14")?
        .trim_start()
        .split(' ')
        .skip(1);
    let masks_hit: usize = masks
        .next()
        .context("parsing step 15")?
        .split(':')
        .nth(1)
        .context("parsing step 16")?
        .parse()
        .context("parsing step 17")?;
    let masks_total: usize = masks
        .next()
        .context("parsing step 18")?
        .split(':')
        .nth(1)
        .context("parsing step 19")?
        .parse()
        .context("parsing step 20")?;
    let masks_hit_per_pkt: f32 = masks
        .next()
        .context("parsing step 21")?
        .split(':')
        .nth(1)
        .context("parsing step 22")?
        .parse()
        .context("parsing step 23")?;

    // cache
    let mut cache = lines
        .next()
        .context("parsing step 24")?
        .trim_start()
        .split(' ')
        .skip(1);
    let cache_hit: usize = cache
        .next()
        .context("parsing step 25")?
        .split(':')
        .nth(1)
        .context("parsing step 26")?
        .parse()
        .context("parsing step 27")?;
    let cache_hit_rate: f32 = cache
        .next()
        .context("parsing step 28")?
        .split(':')
        .nth(1)
        .context("parsing step 29")?
        .strip_suffix('%')
        .context("parsing step 30")?
        .parse()
        .context("parsing step 31")?;

    //caches
    let mut lines = lines.skip(1);

    // masks-cache
    let cache_masks_size: usize = lines
        .next()
        .context("parsing step 32")?
        .split(':')
        .rev()
        .next()
        .context("parsing step 33")?
        .parse()
        .context("parsing step 34")?;

    Ok(OVSStats {
        ms_since_start: Instant::now().duration_since(program_start).as_millis() as u64,
        lookup_hit,
        lookup_missed,
        lookup_lost,
        flows,
        masks_hit,
        masks_total,
        masks_hit_per_pkt,
        cache_hit,
        cache_hit_rate,
        cache_masks_size,
    })
}
