use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::LawArchiveRecord;

pub fn append(root: &Path, record: &LawArchiveRecord) -> Result<()> {
    append_jsonl_atomic(&root.join("archives/law_archive.jsonl"), record)
}
