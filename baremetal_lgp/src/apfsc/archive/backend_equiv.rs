use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::BackendEquivReceipt;

pub fn append_receipt(root: &Path, receipt: &BackendEquivReceipt) -> Result<()> {
    append_jsonl_atomic(&root.join("archive/backend_equiv.jsonl"), receipt)
}
