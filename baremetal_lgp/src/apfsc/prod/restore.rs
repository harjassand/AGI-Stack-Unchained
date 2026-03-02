use std::path::Path;

use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::prod::backup::verify_backup;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct RestoreReport {
    pub backup_id: String,
    pub mode: String,
    pub restored_files: usize,
}

pub fn restore_dry_run(backup_dir: &Path) -> Result<RestoreReport> {
    let manifest = verify_backup(backup_dir)?;
    Ok(RestoreReport {
        backup_id: manifest.backup_id,
        mode: "dry-run".to_string(),
        restored_files: manifest.files.len(),
    })
}

pub fn restore_apply(backup_dir: &Path, target_root: &Path) -> Result<RestoreReport> {
    let manifest = verify_backup(backup_dir)?;
    for rel in manifest.files.keys() {
        if rel == "manifest.json" {
            continue;
        }
        let src = backup_dir.join(rel);
        let dst = target_root.join(rel);
        if let Some(parent) = dst.parent() {
            std::fs::create_dir_all(parent).map_err(|e| io_err(parent, e))?;
        }
        let body = std::fs::read(&src).map_err(|e| io_err(&src, e))?;
        crate::apfsc::artifacts::write_bytes_atomic(&dst, &body)?;
    }

    validate_restored_state(target_root)?;
    Ok(RestoreReport {
        backup_id: manifest.backup_id,
        mode: "apply".to_string(),
        restored_files: manifest.files.len(),
    })
}

fn validate_restored_state(target_root: &Path) -> Result<()> {
    let required_pointers = ["active_candidate", "active_snapshot"];
    for ptr in required_pointers {
        if !target_root.join("pointers").join(ptr).exists() {
            return Err(ApfscError::Validation(format!(
                "restored pointers missing {}",
                ptr
            )));
        }
    }
    if !target_root.join("control").join("control.db").exists() {
        return Err(ApfscError::Validation(
            "restored control db snapshot missing".to_string(),
        ));
    }
    Ok(())
}
