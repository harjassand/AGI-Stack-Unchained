use std::collections::BTreeMap;

use baremetal_lgp::apfsc::normalization::{
    improved_family_ids_from_static_holdout_deltas, weighted_static_score_from_family_bpb,
};
use baremetal_lgp::apfsc::types::{
    ConstellationManifest, FamilyKind, FamilySpec, FamilyWeights, NormalizationPolicy,
    ProtectionFloor, TransferAdaptSpec,
};

fn mock_constellation() -> ConstellationManifest {
    let fam_a = FamilySpec {
        family_id: "det_micro".to_string(),
        family_kind: FamilyKind::AlgorithmicSymbolic,
        base_pack_hash: "a".to_string(),
        transfer_pack_hashes: vec!["ta".to_string()],
        robust_pack_hashes: vec!["ra".to_string()],
        challenge_pack_hashes: vec![],
        weights: FamilyWeights {
            static_weight: 0.75,
            transfer_weight: 0.5,
            robust_weight: 0.5,
        },
        floors: ProtectionFloor {
            protected: true,
            max_static_regress_bpb: 0.001,
            max_transfer_regress_bpb: 0.002,
            max_robust_regress_bpb: 0.002,
            min_family_improve_bpb: 0.0005,
        },
        transfer_adapt: TransferAdaptSpec {
            steps: 1,
            lr: 0.01,
            eps: 1e-8,
            l2: 1e-5,
            clip_grad: 1.0,
            batch_windows: 1,
            max_fast_weight_bytes: 1024,
            max_delta_bits: 4096,
            reset_ephemeral_state: true,
            mutable_surfaces: vec!["nuisance_head".to_string()],
        },
    };

    let fam_b = FamilySpec {
        family_id: "sensor_temporal".to_string(),
        family_kind: FamilyKind::SensoryTemporal,
        base_pack_hash: "b".to_string(),
        transfer_pack_hashes: vec!["tb".to_string()],
        robust_pack_hashes: vec!["rb".to_string()],
        challenge_pack_hashes: vec![],
        weights: FamilyWeights {
            static_weight: 0.25,
            transfer_weight: 0.5,
            robust_weight: 0.5,
        },
        floors: ProtectionFloor {
            protected: false,
            max_static_regress_bpb: 0.002,
            max_transfer_regress_bpb: 0.003,
            max_robust_regress_bpb: 0.003,
            min_family_improve_bpb: 0.0005,
        },
        transfer_adapt: fam_a.transfer_adapt.clone(),
    };

    ConstellationManifest {
        constellation_id: "cid".to_string(),
        snapshot_hash: "snap".to_string(),
        family_specs: vec![fam_a, fam_b],
        fresh_families: Vec::new(),
        normalization: NormalizationPolicy {
            codelen_ref_bytes: 4096,
            transfer_ref_bytes: 4096,
            min_improved_families: 2,
            min_nonprotected_improved_families: 1,
            require_target_subset_hit: true,
            target_subset: vec!["det_micro".to_string()],
            public_static_margin_bpb: 0.001,
            holdout_static_margin_bpb: 0.001,
            holdout_transfer_margin_bpb: 0.0,
            holdout_robust_margin_bpb: 0.0,
        },
        protocol_version: "v".to_string(),
        manifest_hash: "h".to_string(),
    }
}

#[test]
fn weighted_static_score_uses_family_weights_and_single_code_penalty() {
    let c = mock_constellation();
    let mut family = BTreeMap::new();
    family.insert("det_micro".to_string(), 2.0);
    family.insert("sensor_temporal".to_string(), 10.0);

    let score = weighted_static_score_from_family_bpb(&c, 0.5, &family);
    // 0.5 + 0.75*2 + 0.25*10 = 4.5
    assert!((score - 4.5).abs() < 1e-9);

    let score2 = weighted_static_score_from_family_bpb(&c, 0.6, &family);
    assert!((score2 - score - 0.1).abs() < 1e-9);
}

#[test]
fn improved_family_counting_is_deterministic() {
    let c = mock_constellation();
    let mut deltas = BTreeMap::new();
    deltas.insert("sensor_temporal".to_string(), 0.0006);
    deltas.insert("det_micro".to_string(), 0.0007);

    let improved = improved_family_ids_from_static_holdout_deltas(&c, &deltas);
    assert_eq!(
        improved,
        vec!["det_micro".to_string(), "sensor_temporal".to_string()]
    );
}
