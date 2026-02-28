pub const ARTIFACT_SCHEMA_VERSION: u32 = 1;
pub const CONTROL_DB_SCHEMA_VERSION: u32 = 1;
pub const CONFIG_SCHEMA_VERSION: u32 = 1;
pub const RELEASE_MANIFEST_VERSION: u32 = 1;

pub fn compatible_versions(
    artifact: u32,
    control_db: u32,
    config: u32,
    release_manifest: u32,
) -> bool {
    artifact == ARTIFACT_SCHEMA_VERSION
        && control_db == CONTROL_DB_SCHEMA_VERSION
        && config == CONFIG_SCHEMA_VERSION
        && release_manifest == RELEASE_MANIFEST_VERSION
}
