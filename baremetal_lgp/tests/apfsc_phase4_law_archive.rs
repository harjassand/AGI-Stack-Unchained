use baremetal_lgp::apfsc::law_archive::{append_record, build_summary, load_records};
use baremetal_lgp::apfsc::types::{LawArchiveRecord, PromotionClass};
use tempfile::tempdir;

#[test]
fn law_archive_is_deterministic_and_stable() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    std::fs::create_dir_all(root.join("archive")).expect("mkdir");
    std::fs::create_dir_all(root.join("archives")).expect("mkdir");
    std::fs::create_dir_all(root.join("law_archive")).expect("mkdir");

    let r1 = LawArchiveRecord {
        record_id: String::new(),
        candidate_hash: "c2".to_string(),
        parent_hashes: vec![],
        searchlaw_hash: "g".to_string(),
        promotion_class: PromotionClass::A,
        source_lane: "truth".to_string(),
        family_outcome_buckets: Default::default(),
        challenge_bucket: 1,
        canary_survived: true,
        yield_points: 2,
        compute_units: 10,
        morphology_hash: "m".to_string(),
        qd_cell_id: "q".to_string(),
        snapshot_hash: "s".to_string(),
        constellation_id: "k".to_string(),
    };
    let r2 = LawArchiveRecord {
        candidate_hash: "c1".to_string(),
        ..r1.clone()
    };

    append_record(&root, r1).expect("append1");
    append_record(&root, r2).expect("append2");

    let rows1 = load_records(&root).expect("load1");
    let rows2 = load_records(&root).expect("load2");
    assert_eq!(rows1, rows2);
    assert_eq!(rows1.len(), 2);

    let summary = build_summary(&root, "g").expect("summary");
    assert_eq!(summary.total_records, 2);
}
