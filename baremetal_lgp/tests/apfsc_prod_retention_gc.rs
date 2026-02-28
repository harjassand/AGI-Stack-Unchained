use baremetal_lgp::apfsc::artifacts::write_pointer;
use baremetal_lgp::apfsc::prod::gc::gc_candidates;
use baremetal_lgp::apfsc::prod::retention::{apply_retention, RetentionPolicy};
use tempfile::tempdir;

#[test]
fn retention_and_gc_do_not_delete_active_candidate() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    std::fs::create_dir_all(root.join("receipts/x")).expect("mkdir");
    std::fs::create_dir_all(root.join("candidates/c_active")).expect("mkdir");
    std::fs::create_dir_all(root.join("candidates/c_old")).expect("mkdir");
    std::fs::create_dir_all(root.join("pointers")).expect("mkdir");
    write_pointer(&root, "active_candidate", "c_active").expect("ptr");

    let _ = apply_retention(
        &root,
        &RetentionPolicy {
            receipt_days: 1,
            public_trace_days: 1,
            candidate_tmp_hours: 1,
            tombstone_days: 1,
            backup_keep_last: 1,
        },
        1,
    )
    .expect("ret");
    let gc = gc_candidates(&root, false).expect("gc");
    assert!(gc.candidates_marked >= 1);
    assert!(root.join("candidates/c_active").exists());
}
