use std::path::{Path, PathBuf};

pub fn validate_rel(value: &str) -> Result<(), String> {
    if value.is_empty() || value.starts_with('/') {
        return Err("INVALID:RUN_SPEC_PATH".to_string());
    }
    let path = Path::new(value);
    if path.is_absolute() {
        return Err("INVALID:RUN_SPEC_PATH".to_string());
    }
    for part in path.components() {
        if part.as_os_str() == ".." {
            return Err("INVALID:RUN_SPEC_PATH".to_string());
        }
    }
    Ok(())
}

pub fn join_rel(base: &Path, rel: &str) -> Result<PathBuf, String> {
    validate_rel(rel)?;
    Ok(base.join(rel))
}
