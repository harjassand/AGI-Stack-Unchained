use baremetal_lgp::apfsc::prod::jobs::idempotency_key;
use baremetal_lgp::apfsc::prod::journal::{append_journal, load_journal, JobState, JournalRecord};
use tempfile::tempdir;

#[test]
fn journal_append_and_idempotency_are_deterministic() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path();
    std::fs::create_dir_all(root.join("control")).expect("control dir");

    let idk = idempotency_key("start", Some("s"), Some("e"), "prod", "req-1").expect("idk");
    append_journal(
        root,
        &JournalRecord {
            job_id: "j1".to_string(),
            run_id: Some("r1".to_string()),
            idempotency_key: idk.clone(),
            stage: "planned".to_string(),
            target_entity_hash: Some("e".to_string()),
            planned_effects: vec!["effect".to_string()],
            created_at: 1,
            state: JobState::Planned,
            receipt_hash: None,
            commit_marker: None,
        },
    )
    .expect("append");

    let rows = load_journal(root).expect("load");
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].idempotency_key, idk);
}
