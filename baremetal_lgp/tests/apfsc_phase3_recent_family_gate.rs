use std::collections::BTreeMap;

use baremetal_lgp::apfsc::fresh_contact::recent_family_gain;
use baremetal_lgp::apfsc::types::{
    ConstellationScoreReceipt, FamilyEvalVector, FamilyFreshnessMeta,
};

fn receipt() -> ConstellationScoreReceipt {
    let mut per_family = BTreeMap::new();
    per_family.insert(
        "event_sparse".to_string(),
        FamilyEvalVector {
            family_id: "event_sparse".to_string(),
            static_public_bpb: None,
            static_holdout_bpb: Some(1.0),
            anchor_bpb: None,
            transfer_public_bpb: None,
            transfer_holdout_bpb: Some(0.9),
            robust_public_bpb: None,
            robust_holdout_bpb: None,
            challenge_stub_bpb: None,
        },
    );
    per_family.insert(
        "formal_alg".to_string(),
        FamilyEvalVector {
            family_id: "formal_alg".to_string(),
            static_public_bpb: None,
            static_holdout_bpb: Some(1.2),
            anchor_bpb: None,
            transfer_public_bpb: None,
            transfer_holdout_bpb: Some(1.1),
            robust_public_bpb: None,
            robust_holdout_bpb: None,
            challenge_stub_bpb: None,
        },
    );

    ConstellationScoreReceipt {
        candidate_hash: "cand".to_string(),
        incumbent_hash: "inc".to_string(),
        snapshot_hash: "snap".to_string(),
        constellation_id: "cid".to_string(),
        protocol_version: "v".to_string(),
        per_family,
        code_penalty_bpb: 0.0,
        weighted_static_public_bpb: None,
        weighted_static_holdout_bpb: Some(1.0),
        weighted_transfer_public_bpb: None,
        weighted_transfer_holdout_bpb: Some(1.0),
        weighted_robust_public_bpb: None,
        weighted_robust_holdout_bpb: None,
        improved_families: vec!["event_sparse".to_string()],
        nonprotected_improved_families: vec!["event_sparse".to_string()],
        regressed_families: Vec::new(),
        protected_floor_pass: true,
        target_subset_pass: true,
        replay_hash: "r".to_string(),
    }
}

#[test]
fn recent_family_gate_uses_only_fresh_families() {
    let transfer = receipt();
    let static_holdout = receipt();

    let fresh = vec![
        FamilyFreshnessMeta {
            family_id: "event_sparse".to_string(),
            admitted_epoch: 0,
            fresh_until_epoch: 8,
        },
        FamilyFreshnessMeta {
            family_id: "formal_alg".to_string(),
            admitted_epoch: 0,
            fresh_until_epoch: 0,
        },
    ];

    let rec = recent_family_gain("cand", "inc", &transfer, &static_holdout, &fresh, 4, -10.0);
    assert_eq!(rec.recent_family_ids, vec!["event_sparse".to_string()]);
    assert!(rec.family_gain_bpb.contains_key("event_sparse"));
    assert!(!rec.family_gain_bpb.contains_key("formal_alg"));
}
