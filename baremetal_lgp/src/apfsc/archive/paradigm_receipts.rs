use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::ParadigmSignature;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct ParadigmReceiptRow {
    pub candidate_hash: String,
    pub incumbent_hash: String,
    pub signature: ParadigmSignature,
    pub class: String,
}

pub fn append_row(root: &Path, row: &ParadigmReceiptRow) -> Result<()> {
    append_jsonl_atomic(&root.join("archive/paradigm_receipts.jsonl"), row)
}
