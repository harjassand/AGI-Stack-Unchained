use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::FormalPackAdmissionReceipt;

pub fn append(root: &Path, row: &FormalPackAdmissionReceipt) -> Result<()> {
    append_jsonl_atomic(&root.join("archives/formal_policy.jsonl"), row)
}
