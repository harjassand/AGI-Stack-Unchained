use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use serde::Serialize;

pub fn append<T: Serialize>(root: &Path, receipt: &T) -> Result<()> {
    append_jsonl_atomic(&root.join("archives/searchlaw_trace.jsonl"), receipt)
}
