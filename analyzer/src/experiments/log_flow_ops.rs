use std::path::Path;

use clap::Parser;

use crate::utils::{external_prog::run_external_program_script, results_uploader::ResultHandler};

#[derive(Parser, Debug)]
pub struct LogFlowOpArgs {}

pub fn run_experiment(_args: LogFlowOpArgs, handler: Box<impl ResultHandler + ?Sized>) {
    // run the actual experiment
    let result =
        run_external_program_script(include_bytes!("log_flow_ops.py"), &["-w", "flow_ops.jsonl"]);

    if let Err(e) = result {
        warn!("python execution error: {}", e);
    }

    // do something with the results
    handler.handle_result(Path::new("flow_ops.jsonl"));
}
