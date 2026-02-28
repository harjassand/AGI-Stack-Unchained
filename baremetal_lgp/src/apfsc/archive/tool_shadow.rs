use std::path::Path;

use crate::apfsc::artifacts::append_jsonl_atomic;
use crate::apfsc::errors::Result;
use crate::apfsc::types::ToolShadowReceipt;

pub fn append(root: &Path, row: &ToolShadowReceipt) -> Result<()> {
    append_jsonl_atomic(&root.join("archives/tool_shadow.jsonl"), row)
}
