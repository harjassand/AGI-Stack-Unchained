use std::path::Path;

use crate::apfsc::errors::{io_err, Result};

pub fn install_launchd_plist(template: &Path, target: &Path) -> Result<()> {
    let body = std::fs::read(template).map_err(|e| io_err(template, e))?;
    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent).map_err(|e| io_err(parent, e))?;
    }
    crate::apfsc::artifacts::write_bytes_atomic(target, &body)
}
