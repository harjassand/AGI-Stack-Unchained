use std::path::Path;

use crate::apfsc::artifacts::{append_jsonl_atomic, digest_json};
use crate::apfsc::errors::Result;
use crate::apfsc::types::CreditLedgerEntry;

pub fn append_credit_entry(
    root: &Path,
    portfolio_id: &str,
    entry: &CreditLedgerEntry,
) -> Result<()> {
    let pdir = root.join("portfolios").join(portfolio_id);
    std::fs::create_dir_all(&pdir).map_err(|e| crate::apfsc::errors::io_err(&pdir, e))?;
    append_jsonl_atomic(&pdir.join("credit_ledger.jsonl"), entry)?;
    append_jsonl_atomic(&root.join("archives/portfolio_trace.jsonl"), entry)?;
    Ok(())
}

pub fn mint_credit(
    root: &Path,
    portfolio_id: &str,
    branch_id: &str,
    delta_credits: i32,
    reason: &str,
    candidate_hash: Option<String>,
    promotion_hash: Option<String>,
) -> Result<CreditLedgerEntry> {
    let mut entry = CreditLedgerEntry {
        entry_id: String::new(),
        branch_id: branch_id.to_string(),
        delta_credits,
        reason: reason.to_string(),
        candidate_hash,
        promotion_hash,
    };
    entry.entry_id = digest_json(&(
        portfolio_id,
        &entry.branch_id,
        entry.delta_credits,
        &entry.reason,
        &entry.candidate_hash,
        &entry.promotion_hash,
    ))?;
    append_credit_entry(root, portfolio_id, &entry)?;
    Ok(entry)
}
