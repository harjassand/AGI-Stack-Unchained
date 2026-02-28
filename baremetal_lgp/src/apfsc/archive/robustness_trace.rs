use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::RobustnessFamilyTrace;

pub fn append_rows(root: &Path, rows: &[RobustnessFamilyTrace]) -> Result<()> {
    for row in rows {
        append_jsonl_atomic(&root.join("archive/robustness_trace.jsonl"), row)?;
    }
    Ok(())
}
