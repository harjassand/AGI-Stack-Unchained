use std::collections::BTreeMap;
use std::path::Path;

use serde_json::{Map, Value};

use crate::kernel_sys;

pub fn read_json(path: &Path) -> Result<Value, String> {
    let raw = kernel_sys::read_to_string(path)?;
    let value: Value = serde_json::from_str(&raw).map_err(|_| "INVALID:SCHEMA_FAIL".to_string())?;
    Ok(value)
}

pub fn write_json(path: &Path, value: &Value) -> Result<(), String> {
    let bytes = canonical_bytes(value)?;
    kernel_sys::write_bytes(path, &[bytes, b"\n".to_vec()].concat())
}

pub fn canonical_bytes(value: &Value) -> Result<Vec<u8>, String> {
    let norm = canonicalize(value);
    let text = serde_json::to_string(&norm).map_err(|_| "INVALID:SCHEMA_FAIL".to_string())?;
    Ok(text.into_bytes())
}

pub fn canonicalize(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut sorted: BTreeMap<String, Value> = BTreeMap::new();
            for (k, v) in map {
                sorted.insert(k.clone(), canonicalize(v));
            }
            let mut out = Map::new();
            for (k, v) in sorted {
                out.insert(k, v);
            }
            Value::Object(out)
        }
        Value::Array(arr) => Value::Array(arr.iter().map(canonicalize).collect()),
        _ => value.clone(),
    }
}
