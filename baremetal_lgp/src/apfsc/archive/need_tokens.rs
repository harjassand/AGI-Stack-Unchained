use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::NeedToken;

pub fn append(root: &Path, row: &NeedToken) -> Result<()> {
    append_jsonl_atomic(&root.join("archives/need_tokens.jsonl"), row)
}
