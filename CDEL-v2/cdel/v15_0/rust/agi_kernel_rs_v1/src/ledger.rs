use std::path::Path;

use serde_json::{json, Value};

use crate::canon;
use crate::hash;
use crate::kernel_sys;

pub struct LedgerWriter {
    path: std::path::PathBuf,
    prev_hash: String,
}

impl LedgerWriter {
    pub fn new(path: &Path) -> Result<Self, String> {
        if let Some(parent) = path.parent() {
            kernel_sys::create_dir_all(parent)?;
        }
        kernel_sys::write_bytes(path, b"")?;
        Ok(Self {
            path: path.to_path_buf(),
            prev_hash: "GENESIS".to_string(),
        })
    }

    pub fn append(&mut self, event_type: &str, payload: Value) -> Result<String, String> {
        let mut event = json!({
            "schema_version": "kernel_ledger_entry_v1",
            "event_ref_hash": "",
            "prev_event_ref_hash": self.prev_hash,
            "event_type": event_type,
            "payload": payload,
        });
        let bytes = canon::canonical_bytes(&event)?;
        let event_hash = hash::sha256_bytes(&bytes)?;
        if let Some(obj) = event.as_object_mut() {
            obj.insert("event_ref_hash".to_string(), Value::String(event_hash.clone()));
        }
        let line = [canon::canonical_bytes(&event)?, b"\n".to_vec()].concat();
        append_bytes(&self.path, &line)?;
        self.prev_hash = event_hash.clone();
        Ok(event_hash)
    }

    pub fn head_hash(&self) -> String {
        self.prev_hash.clone()
    }
}

fn append_bytes(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let mut current = if kernel_sys::exists(path) {
        kernel_sys::read_bytes(path)?
    } else {
        Vec::new()
    };
    current.extend_from_slice(bytes);
    kernel_sys::write_bytes(path, &current)
}
