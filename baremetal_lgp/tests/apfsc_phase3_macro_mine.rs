use baremetal_lgp::apfsc::archive::family_scores::FamilyScoreRow;
use baremetal_lgp::apfsc::artifacts::{append_jsonl_atomic, ensure_layout};
use baremetal_lgp::apfsc::macro_mine::mine_macros;
use tempfile::tempdir;

fn row(idx: usize, gain: f64) -> FamilyScoreRow {
    FamilyScoreRow {
        candidate_hash: format!("c{idx}"),
        incumbent_hash: "i".to_string(),
        snapshot_hash: "snap".to_string(),
        constellation_id: "cid".to_string(),
        stage: "public_static".to_string(),
        weighted_static_public_bpb: Some(gain),
        weighted_static_holdout_bpb: Some(gain),
        weighted_transfer_public_bpb: None,
        weighted_transfer_holdout_bpb: None,
        weighted_robust_public_bpb: None,
        weighted_robust_holdout_bpb: None,
        improved_families: vec!["event_sparse".to_string()],
        regressed_families: Vec::new(),
        protected_floor_pass: true,
        target_subset_pass: true,
        replay_hash: format!("r{idx}"),
    }
}

#[test]
fn macro_mining_accepts_and_rejects_by_thresholds() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    ensure_layout(&root).expect("layout");

    for i in 0..5 {
        append_jsonl_atomic(&root.join("archive/family_scores.jsonl"), &row(i, 0.01)).expect("row");
    }

    let (_registry1, receipts1) = mine_macros(&root, "snap", "v", 3, 0.001, 1.20, 8).expect("mine 1");
    assert!(receipts1.iter().any(|r| r.accepted));

    let (_registry2, receipts2) = mine_macros(&root, "snap", "v", 99, 10.0, 99.0, 8).expect("mine 2");
    assert!(receipts2.iter().all(|r| !r.accepted));
}
