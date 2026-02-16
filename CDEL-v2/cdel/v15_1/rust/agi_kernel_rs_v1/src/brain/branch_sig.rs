use serde::Serialize;

use crate::{canon, hash};

pub fn branch_signature<T: Serialize>(rule_path: &T) -> Result<String, String> {
    let value = serde_json::to_value(rule_path).map_err(|_| "INVALID:SCHEMA_FAIL".to_string())?;
    let bytes = canon::canonical_bytes(&value)?;
    hash::sha256_bytes(&bytes)
}
