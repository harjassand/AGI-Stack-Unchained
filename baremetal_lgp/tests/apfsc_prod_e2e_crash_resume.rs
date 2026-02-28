use baremetal_lgp::apfsc::prod::control_db::open_control_db;
use baremetal_lgp::apfsc::prod::journal::{append_journal, JobState, JournalRecord};
use baremetal_lgp::apfsc::prod::recovery::startup_recovery;
use tempfile::tempdir;

#[test]
fn crash_resume_marks_incomplete_job_for_recovery() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path();
    std::fs::create_dir_all(root.join("control")).expect("mkdir");

    let conn = open_control_db(&root.join("control/control.db")).expect("db");
    conn.execute(
        "INSERT INTO jobs(job_id, run_id, kind, state, attempt) VALUES('j-crash','r','run','Leased',0)",
        [],
    )
    .expect("insert");

    append_journal(
        root,
        &JournalRecord {
            job_id: "j-crash".to_string(),
            run_id: Some("r".to_string()),
            idempotency_key: "k".to_string(),
            stage: "before_activation".to_string(),
            target_entity_hash: Some("c1".to_string()),
            planned_effects: vec!["activate".to_string()],
            created_at: 1,
            state: JobState::Leased,
            receipt_hash: None,
            commit_marker: None,
        },
    )
    .expect("journal");

    let r = startup_recovery(root, &conn).expect("recover");
    assert!(r.restarted_jobs.contains(&"j-crash".to_string()));
}
