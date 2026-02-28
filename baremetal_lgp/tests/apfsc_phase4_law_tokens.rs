use std::collections::BTreeMap;

use baremetal_lgp::apfsc::law_tokens::distill_law_tokens;
use baremetal_lgp::apfsc::types::{LawArchiveRecord, PromotionClass};

fn rec(id: &str) -> LawArchiveRecord {
    LawArchiveRecord {
        record_id: id.to_string(),
        candidate_hash: id.to_string(),
        parent_hashes: vec![],
        searchlaw_hash: "g".to_string(),
        promotion_class: PromotionClass::A,
        source_lane: "truth".to_string(),
        family_outcome_buckets: BTreeMap::new(),
        challenge_bucket: 1,
        canary_survived: true,
        yield_points: 2,
        compute_units: 10,
        morphology_hash: "m1".to_string(),
        qd_cell_id: "q1".to_string(),
        snapshot_hash: "s".to_string(),
        constellation_id: "c".to_string(),
    }
}

#[test]
fn law_tokens_require_support_and_are_stable() {
    let rows = vec![rec("a"), rec("b"), rec("c")];
    let tokens = distill_law_tokens(&rows, 8).expect("tokens");
    assert!(!tokens.is_empty());
    assert!(tokens[0].support_count >= 2);

    let low = vec![rec("z")];
    let none = distill_law_tokens(&low, 8).expect("low");
    assert!(none.is_empty());
}
