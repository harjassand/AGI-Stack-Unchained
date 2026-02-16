use std::path::Path;

use crate::kernel_sys;

pub fn sha256_file(path: &Path) -> Result<String, String> {
    let hex = kernel_sys::sha256_file(path)?;
    Ok(format!("sha256:{hex}"))
}

pub fn sha256_bytes(bytes: &[u8]) -> Result<String, String> {
    let hex = kernel_sys::sha256_bytes(bytes)?;
    Ok(format!("sha256:{hex}"))
}
