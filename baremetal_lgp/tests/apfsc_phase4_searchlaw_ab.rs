use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::search_law::seed_search_law;
use baremetal_lgp::apfsc::searchlaw_eval::{evaluate_searchlaw_ab, evaluate_searchlaw_offline};
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
        yield_points: 100,
        compute_units: 100,
        morphology_hash: "m".to_string(),
        qd_cell_id: "q".to_string(),
        snapshot_hash: "s".to_string(),
        constellation_id: "k".to_string(),
    }
}

#[test]
fn searchlaw_ab_uses_yield_per_compute_threshold() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let mut cfg = Phase1Config::default();
    cfg.phase4.searchlaw_required_yield_improvement = 0.10;

    let mut cand = seed_search_law();
    cand.lane_weights_q16.insert("truth".to_string(), 65535);
    cand.recombination_rate_q16 = 65535;
    cand.manifest_hash = baremetal_lgp::apfsc::artifacts::digest_json(&cand).expect("hash");

    let inc = seed_search_law();
    let offline =
        evaluate_searchlaw_offline(&root, &cand, &[rec()], "s", "k", &cfg.protocol.version)
            .expect("offline");
    let ab = evaluate_searchlaw_ab(
        &root,
        &cand,
        &inc,
        &offline,
        &[rec()],
        2,
        &cfg,
        "s",
        "k",
        &cfg.protocol.version,
    )
    .expect("ab");

    assert!(ab.candidate_yield_per_compute.is_finite());
    assert!(ab.candidate_yield_per_compute >= 0.0);
}

#[test]
fn searchlaw_ab_rejects_epoch_count_outside_config_range() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let mut cfg = Phase1Config::default();
    cfg.phase4.searchlaw_min_ab_epochs = 2;
    cfg.phase4.searchlaw_max_ab_epochs = 4;

    let cand = seed_search_law();
    let inc = seed_search_law();
    let offline =
        evaluate_searchlaw_offline(&root, &cand, &[rec()], "s", "k", &cfg.protocol.version)
            .expect("offline");
    let err = evaluate_searchlaw_ab(
        &root,
        &cand,
        &inc,
        &offline,
        &[rec()],
        1,
        &cfg,
        "s",
        "k",
        &cfg.protocol.version,
    )
    .expect_err("ab epoch bounds should fail");

    assert!(err.to_string().contains("ab_epochs=1"));
}
