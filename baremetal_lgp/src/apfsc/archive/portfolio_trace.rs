use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use serde::Serialize;

pub fn append<T: Serialize>(root: &Path, row: &T) -> Result<()> {
    append_jsonl_atomic(&root.join("archives/portfolio_trace.jsonl"), row)
}
