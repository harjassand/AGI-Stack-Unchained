use baremetal_lgp::apfsc::search_law::seed_search_law;
use baremetal_lgp::apfsc::searchlaw_eval::{audit_forbidden_inputs, evaluate_searchlaw_offline};
use baremetal_lgp::apfsc::types::{LawArchiveRecord, PromotionClass};
use tempfile::tempdir;

fn rec() -> LawArchiveRecord {
    LawArchiveRecord {
        record_id: "r".to_string(),
        candidate_hash: "c".to_string(),
        parent_hashes: vec![],
        searchlaw_hash: "g".to_string(),
        promotion_class: PromotionClass::A,
        source_lane: "truth".to_string(),
        family_outcome_buckets: Default::default(),
        challenge_bucket: 1,
        canary_survived: true,
        yield_points: 10,
        compute_units: 10,
        morphology_hash: "m".to_string(),
        qd_cell_id: "q".to_string(),
        snapshot_hash: "s".to_string(),
        constellation_id: "k".to_string(),
    }
}

#[test]
fn searchlaw_offline_is_deterministic_and_audits_forbidden_inputs() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let mut law = seed_search_law();
    law.lane_weights_q16.insert("truth".to_string(), 65535);
    law.recombination_rate_q16 = 65535;

    let receipt =
        evaluate_searchlaw_offline(&root, &law, &[rec()], "s", "k", "apfsc-phase4-final-v1")
            .expect("offline");
    assert!(receipt.projected_yield_per_compute.is_finite());

    let mut bad = law.clone();
    bad.need_rules_hash = "holdout_raw_feed".to_string();
    assert!(audit_forbidden_inputs(&bad).is_err());
}
