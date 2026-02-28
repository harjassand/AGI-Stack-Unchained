use baremetal_lgp::apfsc::prod::audit::{append_audit_event, verify_audit_chain, AuditEvent};
use baremetal_lgp::apfsc::prod::control_db::open_control_db;
use tempfile::tempdir;

#[test]
fn audit_hash_chain_is_continuous() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    std::fs::create_dir_all(root.join("archives")).expect("mkdir");
    let conn = open_control_db(&root.join("control/control.db")).expect("db");

    for i in 0..3 {
        append_audit_event(
            &root,
            &conn,
            AuditEvent {
                seq: 0,
                prev_hash: None,
                event_hash: String::new(),
                actor: "op".to_string(),
                role: "Operator".to_string(),
                command: "status".to_string(),
                request_digest: format!("r{}", i),
                result: "ok".to_string(),
                ts: i,
                body_redacted_json: serde_json::json!({"i": i}),
            },
        )
        .expect("append");
    }
    verify_audit_chain(&root).expect("verify");
}
