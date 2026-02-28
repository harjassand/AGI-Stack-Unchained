use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::apfsc::errors::{io_err, ApfscError, Result};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProdPaths {
    pub root: String,
    pub artifacts: String,
    pub archives: String,
    pub backups: String,
    pub control_db: String,
    pub control_socket: String,
    pub metrics_bind: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProdAuth {
    pub enable_control_socket_tokens: bool,
    pub token_file: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProdRelease {
    pub require_signed_artifacts: bool,
    pub require_sbom: bool,
    pub require_provenance: bool,
    pub require_green_release_qual: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProdRuntimeConfig {
    pub paths: ProdPaths,
    pub auth: ProdAuth,
    pub release: ProdRelease,
}

impl Default for ProdRuntimeConfig {
    fn default() -> Self {
        Self {
            paths: ProdPaths {
                root: ".apfsc".to_string(),
                artifacts: "artifacts".to_string(),
                archives: "archives".to_string(),
                backups: "backups".to_string(),
                control_db: "control/control.db".to_string(),
                control_socket: "run/apfscd.sock".to_string(),
                metrics_bind: "127.0.0.1:9464".to_string(),
            },
            auth: ProdAuth {
                enable_control_socket_tokens: true,
                token_file: "secrets/control_tokens.json".to_string(),
            },
            release: ProdRelease {
                require_signed_artifacts: true,
                require_sbom: true,
                require_provenance: true,
                require_green_release_qual: true,
            },
        }
    }
}

fn merge_value(dst: &mut toml::Value, src: &toml::Value) {
    match (dst, src) {
        (toml::Value::Table(a), toml::Value::Table(b)) => {
            for (k, v) in b {
                if let Some(cur) = a.get_mut(k) {
                    merge_value(cur, v);
                } else {
                    a.insert(k.clone(), v.clone());
                }
            }
        }
        (d, s) => *d = s.clone(),
    }
}

pub fn load_layered_config(
    base: &Path,
    profile: &Path,
    local_override: Option<&Path>,
) -> Result<ProdRuntimeConfig> {
    let mut v: toml::Value =
        toml::from_str(&std::fs::read_to_string(base).map_err(|e| io_err(base, e))?)
            .map_err(ApfscError::TomlDecode)?;

    let pv: toml::Value =
        toml::from_str(&std::fs::read_to_string(profile).map_err(|e| io_err(profile, e))?)
            .map_err(ApfscError::TomlDecode)?;
    merge_value(&mut v, &pv);

    if let Some(local) = local_override {
        if local.exists() {
            let lv: toml::Value =
                toml::from_str(&std::fs::read_to_string(local).map_err(|e| io_err(local, e))?)
                    .map_err(ApfscError::TomlDecode)?;
            merge_value(&mut v, &lv);
        }
    }

    if let Ok(root) = std::env::var("APFSC_ROOT") {
        v["paths"]["root"] = toml::Value::String(root);
    }
    if let Ok(token) = std::env::var("APFSC_TOKEN_FILE") {
        v["auth"]["token_file"] = toml::Value::String(token);
    }

    v.try_into()
        .map_err(|e| ApfscError::Validation(format!("invalid production config: {e}")))
}

pub fn resolve_paths(cfg: &ProdRuntimeConfig) -> (PathBuf, PathBuf, PathBuf) {
    let root = PathBuf::from(&cfg.paths.root);
    (
        root.clone(),
        root.join(&cfg.paths.control_db),
        root.join(&cfg.paths.control_socket),
    )
}
