use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::types::WarmRefinementPack;

pub fn validate_warm_refinement(pack: &WarmRefinementPack) -> Result<()> {
    if pack.protected_families.is_empty() {
        return Err(ApfscError::Validation(
            "WarmRefinementPack.protected_families must be non-empty".to_string(),
        ));
    }
    if pack.migration_policy.trim().is_empty() {
        return Err(ApfscError::Validation(
            "WarmRefinementPack.migration_policy must be non-empty".to_string(),
        ));
    }
    Ok(())
}
