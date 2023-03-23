pub mod blast;
pub mod external_prog;
pub mod latency;
pub mod ovs;
pub mod results_uploader;
pub mod tcpdump;

pub fn dump_file(name: &str, ext: &str) -> String {
    format!("{}_{}.{}", name, chrono::Local::now().to_rfc3339(), ext)
}
