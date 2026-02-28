use std::path::Path;

use crate::apfsc::artifacts::{read_pointer, write_pointer};
use crate::apfsc::errors::Result;

pub fn read_active_search_law(root: &Path) -> Result<String> {
    read_pointer(root, "active_search_law")
}

pub fn write_active_search_law(root: &Path, searchlaw_hash: &str) -> Result<()> {
    write_pointer(root, "active_search_law", searchlaw_hash)
}

pub fn read_active_formal_policy(root: &Path) -> Result<String> {
    read_pointer(root, "active_formal_policy")
}

pub fn write_active_formal_policy(root: &Path, policy_hash: &str) -> Result<()> {
    write_pointer(root, "active_formal_policy", policy_hash)
}
