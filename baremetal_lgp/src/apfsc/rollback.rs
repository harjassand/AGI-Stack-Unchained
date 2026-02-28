use std::path::Path;

use crate::apfsc::artifacts::{read_pointer, write_pointer};
use crate::apfsc::errors::Result;

pub fn stage_rollback_target(root: &Path, incumbent_hash: &str) -> Result<()> {
    write_pointer(root, "rollback_candidate", incumbent_hash)
}

pub fn ensure_rollback_target_exists(root: &Path) -> Result<String> {
    read_pointer(root, "rollback_candidate")
}

pub fn restore_rollback_target(root: &Path) -> Result<String> {
    let rollback = ensure_rollback_target_exists(root)?;
    write_pointer(root, "active_candidate", &rollback)?;
    Ok(rollback)
}
