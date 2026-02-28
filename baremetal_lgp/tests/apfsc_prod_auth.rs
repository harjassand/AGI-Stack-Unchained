use baremetal_lgp::apfsc::prod::auth::{authorize, resolve_role, Role, TokenFile, TokenRecord};
use tempfile::tempdir;

#[test]
fn auth_resolves_role_and_enforces_permissions() {
    let tmp = tempdir().expect("tmp");
    let file = tmp.path().join("tokens.json");
    let tf = TokenFile {
        tokens: vec![TokenRecord {
            actor: "alice".to_string(),
            role: Role::Operator,
            token: "secret".to_string(),
        }],
    };
    std::fs::write(&file, serde_json::to_vec(&tf).expect("json")).expect("write");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&file, std::fs::Permissions::from_mode(0o600)).expect("chmod");
    }
    let role = resolve_role(&file, "alice", Some("secret")).expect("role");
    authorize(role, Role::Reader).expect("auth");
    assert!(authorize(Role::Reader, Role::Operator).is_err());
}
