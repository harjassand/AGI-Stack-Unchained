use baremetal_lgp::apfsc::prod::compaction::compact_archives;
use tempfile::tempdir;

#[test]
fn compaction_rewrites_jsonl_segments() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    std::fs::create_dir_all(root.join("archives")).expect("mkdir");
    std::fs::write(root.join("archives/a.jsonl"), b"{}\n{}\n").expect("write");

    let r = compact_archives(&root, false).expect("compact");
    assert_eq!(r.files_compacted, 1);
    assert!(root.join("archives/a.jsonl.zst").exists());
}
