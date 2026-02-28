use crate::apfsc::artifacts::digest_json;
use crate::apfsc::errors::Result;

pub fn idempotency_key(
    command_type: &str,
    snapshot_hash: Option<&str>,
    entity_hash: Option<&str>,
    profile: &str,
    operator_request_uuid: &str,
) -> Result<String> {
    digest_json(&(
        command_type,
        snapshot_hash.unwrap_or_default(),
        entity_hash.unwrap_or_default(),
        profile,
        operator_request_uuid,
    ))
}

pub fn now_unix_s() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
