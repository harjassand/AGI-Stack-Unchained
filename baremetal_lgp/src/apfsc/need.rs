use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::NeedToken;

fn pioneer_mode_active(root: &Path) -> bool {
    crate::apfsc::artifacts::read_pointer(root, "active_epoch_mode")
        .map(|m| m.eq_ignore_ascii_case("pioneer"))
        .unwrap_or(false)
}

pub fn emit_need_tokens(root: &Path, tokens: &[NeedToken]) -> Result<()> {
    let capped = tokens
        .iter()
        .filter(|t| !t.token_id.is_empty())
        .collect::<Vec<_>>();
    let (archive_path, archives_path) = if pioneer_mode_active(root) {
        (
            root.join("archive").join("incubator_need_tokens.jsonl"),
            root.join("archives").join("incubator_need_tokens.jsonl"),
        )
    } else {
        (
            root.join("archive").join("need_tokens.jsonl"),
            root.join("archives").join("need_tokens.jsonl"),
        )
    };
    for token in capped {
        append_jsonl_atomic(&archive_path, token)?;
        append_jsonl_atomic(&archives_path, token)?;
    }
    Ok(())
}
