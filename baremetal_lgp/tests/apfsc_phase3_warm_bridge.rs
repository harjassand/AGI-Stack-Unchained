use baremetal_lgp::apfsc::bridge::validate_warm_refinement;
use baremetal_lgp::apfsc::types::WarmRefinementPack;

#[test]
fn warm_refinement_pack_passes_and_fails_on_mapping_constraints() {
    let pass = WarmRefinementPack {
        observable_map_hash: Some("obs_map".to_string()),
        state_map_hash: Some("state_map".to_string()),
        tolerance_spec_hash: Some("tol".to_string()),
        protected_head_ids: vec!["native_head".to_string()],
        protected_families: vec!["det_micro".to_string()],
        max_anchor_regress_bits: 0.0,
        max_public_regress_bits: 0.0,
        migration_policy: "warm_v1".to_string(),
    };
    validate_warm_refinement(&pass).expect("pass warm pack");

    let fail = WarmRefinementPack {
        observable_map_hash: Some("".to_string()),
        state_map_hash: Some("state_map".to_string()),
        tolerance_spec_hash: Some("tol".to_string()),
        protected_head_ids: vec!["native_head".to_string()],
        protected_families: vec!["det_micro".to_string()],
        max_anchor_regress_bits: 0.0,
        max_public_regress_bits: 0.0,
        migration_policy: "warm_v1".to_string(),
    };
    assert!(validate_warm_refinement(&fail).is_err());
}
