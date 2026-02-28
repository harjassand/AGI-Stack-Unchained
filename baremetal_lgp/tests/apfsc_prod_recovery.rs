use baremetal_lgp::apfsc::prod::control_db::open_control_db;
use baremetal_lgp::apfsc::prod::journal::{append_journal, JobState, JournalRecord};
use baremetal_lgp::apfsc::prod::recovery::startup_recovery;
use tempfile::tempdir;

#[test]
fn startup_recovery_moves_running_jobs_to_recovery_pending() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path();
    std::fs::create_dir_all(root.join("control")).expect("control");
    let conn = open_control_db(&root.join("control/control.db")).expect("db");
    conn.execute(
        "INSERT INTO jobs(job_id, run_id, kind, state, attempt) VALUES('j1','r1','run','Running',0)",
        [],
    )
    .expect("insert");

    append_journal(
        root,
        &JournalRecord {
            job_id: "j1".to_string(),
            run_id: Some("r1".to_string()),
            idempotency_key: "k".to_string(),
            stage: "run".to_string(),
            target_entity_hash: None,
            planned_effects: vec!["x".to_string()],
            created_at: 1,
            state: JobState::Running,
            receipt_hash: None,
            commit_marker: None,
        },
    )
    .expect("journal");

    let r = startup_recovery(root, &conn).expect("recover");
    assert_eq!(r.restarted_jobs, vec!["j1".to_string()]);
}
