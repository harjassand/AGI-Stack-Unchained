use std::io::{Read, Write};
use std::os::unix::net::UnixStream;

use baremetal_lgp::apfsc::prod::control_api::{ControlCommand, ControlRequest, ControlResponse};
use baremetal_lgp::apfsc::prod::control_db::open_control_db;
use baremetal_lgp::apfsc::prod::daemon::serve_once;
use baremetal_lgp::apfsc::prod::service::ServiceContext;
use baremetal_lgp::apfsc::prod::telemetry::Telemetry;
use tempfile::tempdir;

#[test]
fn daemon_round_trip_over_local_socket() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    std::fs::create_dir_all(root.join("secrets")).expect("mkdir");
    std::fs::create_dir_all(root.join("control")).expect("mkdir");
    std::fs::create_dir_all(root.join("pointers")).expect("mkdir");

    let tokens = serde_json::json!({
        "tokens": [
            {"actor":"operator","role":"Operator","token":"secret"},
            {"actor":"reader","role":"Reader","token":"read"},
            {"actor":"release","role":"ReleaseManager","token":"rel"}
        ]
    });
    let token_file = root.join("secrets/control_tokens.json");
    std::fs::write(
        &token_file,
        serde_json::to_vec_pretty(&tokens).expect("json"),
    )
    .expect("write");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&token_file, std::fs::Permissions::from_mode(0o600))
            .expect("chmod");
    }

    let conn = open_control_db(&root.join("control/control.db")).expect("db");
    let mut ctx = ServiceContext::new(
        root.clone(),
        root.join("backups"),
        conn,
        Telemetry::default(),
    );

    let (mut server, mut client) = UnixStream::pair().expect("pair");
    let req = ControlRequest {
        request_id: "r1".to_string(),
        actor: "operator".to_string(),
        token: Some("secret".to_string()),
        command: ControlCommand::Status,
    };
    client
        .write_all(&serde_json::to_vec(&req).expect("json"))
        .expect("write");
    client
        .shutdown(std::net::Shutdown::Write)
        .expect("shutdown");

    serve_once(&root, &token_file, &mut server, &mut ctx).expect("serve");
    drop(server);
    let mut out = Vec::new();
    client.read_to_end(&mut out).expect("read");
    let resp: ControlResponse = serde_json::from_slice(&out).expect("resp");
    assert!(resp.ok);
}
