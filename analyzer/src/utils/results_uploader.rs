use std::{path::Path, env};

pub trait ResultHandler {
    fn handle_result(&self, path: &Path);
}

pub struct ResultIgnorer {}

impl ResultIgnorer {
    pub fn new() -> ResultIgnorer {
        ResultIgnorer {}
    }
}

impl ResultHandler for ResultIgnorer {
    fn handle_result(&self, _path: &Path) {}
}

pub struct ResultsUploader {
    push_url: String,
}

impl ResultsUploader {
    pub fn new(url: String) -> Self {
        Self { push_url: url }
    }
}

impl ResultHandler for ResultsUploader {
    fn handle_result(&self, file: &Path) {
        if !file.exists() {
            error!(
                "can't handle result file which does not exist, '{}'",
                file.display()
            );
            return;
        }

        let res = subprocess::Exec::cmd("curl")
            .arg(&self.push_url)
            .arg("-T")
            .arg(file.as_os_str())
            .join();

        match res {
            Ok(exit) => info!(
                "result file '{}' uploaded, exit code {:?}",
                file.display(),
                exit
            ),
            Err(err) => error!(
                "failed to upload results file '{}', error: {:?}",
                file.display(),
                err
            ),
        };
    }
}
