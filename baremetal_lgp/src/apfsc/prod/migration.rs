use std::path::Path;

use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::prod::control_db::{control_db_schema_version, open_control_db};
use crate::apfsc::prod::versioning::CONTROL_DB_SCHEMA_VERSION;

pub fn migrate_control_db(path: &Path, from: u32, to: u32, dry_run: bool) -> Result<()> {
    if from > to {
        return Err(ApfscError::Unsupported(
            "downgrade is unsupported without restore".to_string(),
        ));
    }
    if dry_run {
        return Ok(());
    }
    let conn = open_control_db(path)?;
    let current = control_db_schema_version(&conn)?;
    if current != CONTROL_DB_SCHEMA_VERSION {
        return Err(ApfscError::Validation(format!(
            "unexpected schema version {} != {}",
            current, CONTROL_DB_SCHEMA_VERSION
        )));
    }
    Ok(())
}
