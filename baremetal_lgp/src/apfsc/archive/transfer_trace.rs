use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::TransferFamilyTrace;

pub fn append_rows(root: &Path, rows: &[TransferFamilyTrace]) -> Result<()> {
    for row in rows {
        append_jsonl_atomic(&root.join("archive/transfer_trace.jsonl"), row)?;
    }
    Ok(())
}
