use baremetal_lgp::apfsc::prod::auth::Role;
use baremetal_lgp::apfsc::prod::control_api::{ControlCommand, ControlRequest};
use baremetal_lgp::apfsc::prod::control_db::open_control_db;
use baremetal_lgp::apfsc::prod::jobs::idempotency_key;
use baremetal_lgp::apfsc::prod::journal::{append_journal, load_journal, JobState, JournalRecord};
use baremetal_lgp::apfsc::prod::service::{handle_request, ServiceContext};
use baremetal_lgp::apfsc::prod::telemetry::Telemetry;
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

#[test]
fn mutating_commands_are_journaled_and_idempotent() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    std::fs::create_dir_all(root.join("control")).expect("control dir");

    let conn = open_control_db(&root.join("control/control.db")).expect("db");
    let mut ctx = ServiceContext::new(
        root.clone(),
        root.join("backups"),
        conn,
        Telemetry::default(),
    );

    let req = ControlRequest {
        request_id: "req-abc".to_string(),
        actor: "operator".to_string(),
        token: None,
        command: ControlCommand::Pause,
    };

    let first = handle_request(&mut ctx, &req, Role::Operator).expect("first");
    assert!(first.ok);
    let rows = load_journal(&root).expect("journal");
    assert!(rows
        .iter()
        .any(|r| matches!(r.state, JobState::Planned) && r.job_id.contains("req-abc")));
    assert!(rows
        .iter()
        .any(|r| matches!(r.state, JobState::Committed) && r.job_id.contains("req-abc")));

    let second = handle_request(&mut ctx, &req, Role::Operator).expect("second");
    assert!(second.ok);
    assert!(second.message.contains("idempotent replay"));
}
