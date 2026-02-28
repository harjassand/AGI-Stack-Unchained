use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::{MacroInductionReceipt, MacroRegistry};

pub fn append_registry(root: &Path, registry: &MacroRegistry) -> Result<()> {
    append_jsonl_atomic(&root.join("archive/macro_registry.jsonl"), registry)
}

pub fn append_induction_receipt(root: &Path, receipt: &MacroInductionReceipt) -> Result<()> {
    append_jsonl_atomic(&root.join("archive/macro_registry.jsonl"), receipt)
}
