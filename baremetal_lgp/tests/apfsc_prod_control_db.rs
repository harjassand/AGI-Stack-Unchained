use baremetal_lgp::apfsc::prod::control_db::{control_db_schema_version, open_control_db};
use tempfile::tempdir;

#[test]
fn control_db_opens_with_wal_and_schema() {
    let tmp = tempdir().expect("tmp");
    let db = tmp.path().join("control.db");
    let conn = open_control_db(&db).expect("open");
    let mode: String = conn
        .query_row("PRAGMA journal_mode", [], |r| r.get(0))
        .expect("pragma");
    assert_eq!(mode.to_lowercase(), "wal");
    assert_eq!(control_db_schema_version(&conn).expect("ver"), 1);
}

#[test]
fn control_db_rejects_bad_schema_checksum() {
    let tmp = tempdir().expect("tmp");
    let db = tmp.path().join("control.db");
    let conn = open_control_db(&db).expect("open");
    conn.execute(
        "UPDATE schema_migrations SET checksum='corrupt' WHERE version=1",
        [],
    )
    .expect("corrupt");
    drop(conn);

    let reopened = open_control_db(&db);
    assert!(reopened.is_err());
}
