use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::NeedToken;

pub fn emit_need_tokens(root: &Path, tokens: &[NeedToken]) -> Result<()> {
    let capped = tokens
        .iter()
        .filter(|t| !t.token_id.is_empty())
        .collect::<Vec<_>>();
    for token in capped {
        append_jsonl_atomic(&root.join("archive/need_tokens.jsonl"), token)?;
        append_jsonl_atomic(&root.join("archives/need_tokens.jsonl"), token)?;
    }
    Ok(())
}
