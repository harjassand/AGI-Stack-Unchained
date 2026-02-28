use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::BridgeReceipt;

pub fn append_receipt(root: &Path, receipt: &BridgeReceipt) -> Result<()> {
    append_jsonl_atomic(&root.join("archive/bridge_trace.jsonl"), receipt)
}
