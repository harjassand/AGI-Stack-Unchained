use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::QdCellRecord;

pub fn append(root: &Path, row: &QdCellRecord) -> Result<()> {
    append_jsonl_atomic(&root.join("archives/qd_archive.jsonl"), row)
}
