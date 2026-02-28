use std::collections::BTreeMap;

use baremetal_lgp::apfsc::need::emit_need_tokens;
use baremetal_lgp::apfsc::search_law::{build_search_plan, seed_search_law};
use baremetal_lgp::apfsc::types::{LawToken, SearchLawFeatureVector};
use tempfile::tempdir;

#[test]
fn need_tokens_emit_with_expected_justifications() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    std::fs::create_dir_all(root.join("archive")).expect("mkdir");
    std::fs::create_dir_all(root.join("archives")).expect("mkdir");

    let law = seed_search_law();
    let features = SearchLawFeatureVector {
        active_family_ids: vec!["det_micro".to_string()],
        stale_family_ids: vec![],
        underfilled_qd_cells: vec!["cell_a".to_string()],
        dominant_failure_modes: vec![],
        recent_public_yield_buckets: BTreeMap::new(),
        recent_judged_yield_points: 0,
        recent_compute_units: 1,
        recent_canary_failures: 0,
        recent_challenge_failures: 0,
        public_plateau_epochs: 2,
    };
    let plan = build_search_plan(&law, &features, &Vec::<LawToken>::new(), 7, 8);
    assert!(!plan.need_tokens.is_empty());
    assert!(plan.need_tokens.iter().any(|t| t
        .justification_codes
        .iter()
        .any(|j| j == "plateau_judged_yield")));
    emit_need_tokens(&root, &plan.need_tokens).expect("emit");
    assert!(root.join("archives/need_tokens.jsonl").exists());
}
