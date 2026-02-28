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
        let dst = map_restore_path(target_root, rel);
        if let Some(parent) = dst.parent() {
            std::fs::create_dir_all(parent).map_err(|e| io_err(parent, e))?;
        }
        let body = std::fs::read(&src).map_err(|e| io_err(&src, e))?;
        crate::apfsc::artifacts::write_bytes_atomic(&dst, &body)?;
    }

    if target_root.join("pointers").exists() {
        let required = ["active_candidate", "active_snapshot"];
        for r in required {
            if !target_root.join("pointers").join(r).exists() {
                return Err(ApfscError::Validation(format!(
                    "restored pointers missing {}",
                    r
                )));
            }
        }
    }

    Ok(RestoreReport {
        backup_id: manifest.backup_id,
        mode: "apply".to_string(),
        restored_files: manifest.files.len(),
    })
}

fn map_restore_path(target_root: &Path, rel: &str) -> std::path::PathBuf {
    match rel {
        "control.db.zst" => target_root.join("control").join("control.db"),
        _ => target_root.join(rel),
    }
}
