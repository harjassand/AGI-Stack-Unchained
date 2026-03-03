use std::path::Path;

use crate::apfsc::artifacts::ensure_layout;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::prod::auth::validate_token_permissions;
use crate::apfsc::prod::profiles::ProdRuntimeConfig;
use crate::apfsc::prod::secrets::validate_secret_permissions;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct PreflightReport {
    pub ok: bool,
    pub checks: Vec<String>,
    pub failures: Vec<String>,
}

pub fn run_preflight(root: &Path, cfg: &ProdRuntimeConfig) -> Result<PreflightReport> {
    ensure_layout(root)?;
    let mut checks = Vec::new();
    let mut failures = Vec::new();

    if crate::apfsc::artifacts::silent_run_enabled() {
        checks.push("omega_silent_run_enabled".to_string());
    } else {
        for dir in [
            root.join("control"),
            root.join("run"),
            root.join("logs"),
            root.join("diagnostics"),
            root.join("backups"),
        ] {
            if let Err(e) = std::fs::create_dir_all(&dir) {
                failures.push(format!("create {} failed: {}", dir.display(), e));
            } else {
                checks.push(format!("dir:{}", dir.display()));
            }
        }
    }

    let token = root.join(&cfg.auth.token_file);
    if token.exists() {
        match validate_token_permissions(&token) {
            Ok(_) => checks.push("token_perms_ok".to_string()),
            Err(e) => failures.push(e.to_string()),
        }
    } else {
        checks.push("token_file_missing_optional".to_string());
    }

    if let Err(e) = validate_secret_permissions(&token) {
        failures.push(e.to_string());
    }

    Ok(PreflightReport {
        ok: failures.is_empty(),
        checks,
        failures,
    })
}

pub fn ensure_preflight(root: &Path, cfg: &ProdRuntimeConfig) -> Result<()> {
    let report = run_preflight(root, cfg)?;
    if report.ok {
        return Ok(());
    }
    Err(ApfscError::Validation(format!(
        "preflight failed: {}",
        report.failures.join("; ")
    )))
}
