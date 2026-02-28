use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::canary::CanaryReceipt;
use crate::apfsc::errors::Result;

pub fn append_receipt(root: &Path, receipt: &CanaryReceipt) -> Result<()> {
    append_jsonl_atomic(&root.join("archive/canary_trace.jsonl"), receipt)
}
