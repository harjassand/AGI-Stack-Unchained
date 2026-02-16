use std::path::Path;

use serde_json::Value;

use crate::tools;

pub fn run(fixture: &Value, reference_root: &Path, state_root: &Path) -> Result<Vec<String>, String> {
    let files = fixture
        .get("reference_files")
        .and_then(Value::as_array)
        .ok_or_else(|| "INVALID:FIXTURE_MATRIX".to_string())?;
    let rels: Vec<String> = files
        .iter()
        .map(|v| v.as_str().unwrap_or_default().to_string())
        .collect();
    tools::copy_rel_files(reference_root, &rels, state_root)
}
