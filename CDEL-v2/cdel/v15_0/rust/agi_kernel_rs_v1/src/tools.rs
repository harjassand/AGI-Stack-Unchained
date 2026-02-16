use std::path::Path;

use crate::kernel_sys;
use crate::paths;

pub fn copy_rel_files(reference_root: &Path, rel_files: &[String], dest_root: &Path) -> Result<Vec<String>, String> {
    let mut copied: Vec<String> = Vec::new();
    for rel in rel_files {
        paths::validate_rel(rel)?;
        let src = reference_root.join(rel);
        let dst = dest_root.join(rel);
        kernel_sys::copy_file(&src, &dst)?;
        copied.push(rel.clone());
    }
    copied.sort();
    Ok(copied)
}

pub fn copy_config_tree(src_root: &Path, dst_root: &Path) -> Result<(), String> {
    let files = kernel_sys::list_files_recursive(src_root)?;
    for src in files {
        let rel = src
            .strip_prefix(src_root)
            .map_err(|_| "INVALID:MISSING_ARTIFACT".to_string())?;
        let dst = dst_root.join(rel);
        kernel_sys::copy_file(&src, &dst)?;
    }
    Ok(())
}
