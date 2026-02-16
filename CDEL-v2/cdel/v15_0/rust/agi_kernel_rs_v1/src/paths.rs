use std::path::{Path, PathBuf};

pub fn validate_rel(path: &str) -> Result<(), String> {
    if path.starts_with('/') {
        return Err("INVALID:RUN_SPEC_PATH".to_string());
    }
    let p = Path::new(path);
    if p.is_absolute() {
        return Err("INVALID:RUN_SPEC_PATH".to_string());
    }
    for part in p.components() {
        if part.as_os_str() == ".." {
            return Err("INVALID:RUN_SPEC_PATH".to_string());
        }
    }
    Ok(())
}

pub fn join_rel(root: &Path, rel: &str) -> Result<PathBuf, String> {
    validate_rel(rel)?;
    Ok(root.join(rel))
}
