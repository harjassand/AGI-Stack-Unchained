use std::path::Path;

use serde::Deserialize;

use crate::canon;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ToolchainManifest {
    checker_name: String,
    invocation_template: Vec<String>,
    checker_executable_hash: String,
    toolchain_id: String,
}

pub fn load_toolchain_manifest(path: &Path) -> Result<(), String> {
    let value = canon::read_json(path)?;
    let manifest: ToolchainManifest =
        serde_json::from_value(value).map_err(|_| "INVALID:TOOLCHAIN_MANIFEST".to_string())?;
    if manifest.checker_name.is_empty() {
        return Err("INVALID:TOOLCHAIN_MANIFEST".to_string());
    }
    if manifest.invocation_template.is_empty() {
        return Err("INVALID:TOOLCHAIN_MANIFEST".to_string());
    }
    let exe = &manifest.invocation_template[0];
    if !exe.starts_with('/') {
        return Err("INVALID:TOOLCHAIN_MANIFEST".to_string());
    }
    if !manifest.checker_executable_hash.starts_with("sha256:")
        || manifest.checker_executable_hash == "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    {
        return Err("INVALID:TOOLCHAIN_MANIFEST".to_string());
    }
    if !manifest.toolchain_id.starts_with("sha256:") {
        return Err("INVALID:TOOLCHAIN_MANIFEST".to_string());
    }
    Ok(())
}
