use baremetal_lgp::apfsc::artifacts::write_pointer;
use baremetal_lgp::apfsc::prod::backup::{create_backup, verify_backup};
use baremetal_lgp::apfsc::prod::control_db::open_control_db;
use baremetal_lgp::apfsc::prod::restore::{restore_apply, restore_dry_run};
use tempfile::tempdir;

#[test]
fn backup_and_restore_round_trip() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join("root");
    std::fs::create_dir_all(root.join("control")).expect("mkdir");
    std::fs::create_dir_all(root.join("pointers")).expect("mkdir");
    write_pointer(&root, "active_candidate", "c1").expect("pointer");
    write_pointer(&root, "active_snapshot", "s1").expect("pointer");

    let conn = open_control_db(&root.join("control/control.db")).expect("db");
    let m = create_backup(&root, &root.join("backups"), &conn).expect("backup");
    let bdir = root.join("backups").join(&m.backup_id);
    verify_backup(&bdir).expect("verify");
    restore_dry_run(&bdir).expect("dry");

    let target = tmp.path().join("restored");
    restore_apply(&bdir, &target).expect("apply");
    assert!(target.join("pointers/active_candidate").exists());
}
