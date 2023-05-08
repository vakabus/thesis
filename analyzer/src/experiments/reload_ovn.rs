use clap::Parser;

use crate::utils::external_prog::run_external_program_script;

#[derive(Parser, Debug)]
pub struct ReloadOvnArgs {}

pub fn run_experiment(_args: ReloadOvnArgs) {
    // run the actual experiment
    let result = run_external_program_script(include_bytes!("reload_ovn.sh"), &[]);

    if let Err(e) = result {
        warn!("script execution error: {}", e);
    }
}
