use std::path::Path;

use serde_json::{json, Value};

use crate::canon;
use crate::hash;
use crate::kernel_sys;

pub fn build_snapshot(root: &Path, root_rel: &str) -> Result<Value, String> {
    let files = kernel_sys::list_files_recursive(root)?;
    let mut rows: Vec<Value> = Vec::new();
    for path in files {
        let rel = path
            .strip_prefix(root)
            .map_err(|_| "INVALID:SNAPSHOT_ROOT".to_string())?
            .to_string_lossy()
            .replace('\\', "/");
        if rel.contains("__pycache__") || rel.ends_with(".pyc") {
            continue;
        }
        let file_hash = hash::sha256_file(&path)?;
        rows.push(json!({"path_rel": rel, "sha256": file_hash}));
    }
    rows.sort_by(|a, b| {
        let pa = a.get("path_rel").and_then(Value::as_str).unwrap_or("");
        let pb = b.get("path_rel").and_then(Value::as_str).unwrap_or("");
        pa.cmp(pb)
    });

    let root_hash = hash::sha256_bytes(&canon::canonical_bytes(&Value::Array(rows.clone()))?)?;
    Ok(json!({
        "schema_version": "immutable_tree_snapshot_v1",
        "root_rel": root_rel,
        "files": rows,
        "root_hash_sha256": root_hash,
    }))
}
