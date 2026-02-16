pub mod omega_v4;
pub mod sas_system_v14;

use std::path::Path;

use serde_json::Value;

pub fn run_protocol(
    capability_id: &str,
    fixture: &Value,
    reference_root: &Path,
    state_root: &Path,
) -> Result<Vec<String>, String> {
    match capability_id {
        "RSI_SAS_SYSTEM_V14_0" => sas_system_v14::run(fixture, reference_root, state_root),
        "RSI_OMEGA_V4_0" => omega_v4::run(fixture, reference_root, state_root),
        _ => Err("INVALID:CAPABILITY_NOT_SUPPORTED".to_string()),
    }
}
