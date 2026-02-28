use baremetal_lgp::apfsc::prod::migration::migrate_control_db;
use tempfile::tempdir;

#[test]
fn migration_dry_run_and_apply_work() {
    let tmp = tempdir().expect("tmp");
    let db = tmp.path().join("control.db");
    migrate_control_db(&db, 1, 1, true).expect("dry run");
    migrate_control_db(&db, 1, 1, false).expect("apply");
}
