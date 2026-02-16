use std::path::Path;

use serde::Deserialize;

use crate::canon;
use crate::hash;
use crate::kernel_sys;

#[derive(Clone, Deserialize)]
pub struct ToolchainManifest {
    pub checker_name: String,
    pub invocation_template: Vec<String>,
    pub checker_executable_hash: String,
    pub toolchain_id: String,
}

pub fn load_toolchain_manifest(path: &Path) -> Result<ToolchainManifest, String> {
    let value = canon::read_json(path)?;
    let obj: ToolchainManifest = serde_json::from_value(value.clone()).map_err(|_| "INVALID:TOOLCHAIN_SCHEMA".to_string())?;
    if obj.checker_name.is_empty() || obj.invocation_template.is_empty() {
        return Err("INVALID:TOOLCHAIN_SCHEMA".to_string());
    }
    if !Path::new(&obj.invocation_template[0]).is_absolute() {
        return Err("INVALID:TOOLCHAIN_PIN".to_string());
    }
    if obj.checker_executable_hash == format!("sha256:{}", "0".repeat(64)) {
        return Err("INVALID:TOOLCHAIN_ZERO_HASH".to_string());
    }

    let exe_hash = hash::sha256_file(Path::new(&obj.invocation_template[0]))?;
    if exe_hash != obj.checker_executable_hash {
        return Err("INVALID:TOOLCHAIN_SPOOF".to_string());
    }

    let mut stripped = value;
    if let Some(map) = stripped.as_object_mut() {
        map.remove("toolchain_id");
    }
    let calc = hash::sha256_bytes(&canon::canonical_bytes(&stripped)?)?;
    if calc != obj.toolchain_id {
        return Err("INVALID:TOOLCHAIN_ID_MISMATCH".to_string());
    }

    Ok(obj)
}

pub fn ensure_native_binary(path: &Path) -> Result<(), String> {
    let raw = kernel_sys::read_bytes(path)?;
    if raw.starts_with(b"#!") {
        return Err("INVALID:KERNEL_BINARY_NOT_NATIVE".to_string());
    }
    let head = if raw.len() > 1024 { &raw[..1024] } else { &raw[..] };
    if !head.is_empty() && !head.contains(&0) {
        if let Ok(text) = std::str::from_utf8(head) {
            let printable = text
                .chars()
                .filter(|c| c.is_ascii_graphic() || c.is_ascii_whitespace())
                .count();
            if printable * 100 / text.len().max(1) > 95 {
                return Err("INVALID:KERNEL_BINARY_NOT_NATIVE".to_string());
            }
        }
    }
    Ok(())
}
