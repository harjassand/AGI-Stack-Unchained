use baremetal_lgp::apfsc::challenge_scheduler::score_hidden_challenge_gate;
use baremetal_lgp::apfsc::search_law::seed_search_law;
use baremetal_lgp::apfsc::searchlaw_eval::audit_forbidden_inputs;
use baremetal_lgp::apfsc::types::{ChallengeRole, HiddenChallengeFamily, HiddenChallengeManifest};

#[test]
fn phase4_judge_style_gates_cover_arch_and_searchlaw() {
    let m = HiddenChallengeManifest {
        constellation_id: "c".to_string(),
        snapshot_hash: "s".to_string(),
        active_hidden_families: vec![HiddenChallengeFamily {
            family_id: "f".to_string(),
            role: ChallengeRole::HiddenGeneralization,
            source_pack_hash: "p".to_string(),
            window_commit_hash: "w".to_string(),
            reveal_epoch: 0,
            retire_after_epoch: 8,
            protected: false,
        }],
        retired_hidden_families: vec![],
        manifest_hash: "h".to_string(),
    };
    let r = score_hidden_challenge_gate("cand", "inc", &m, "v").expect("challenge");
    assert!(r.aggregate_bucket_score >= -2);

    let mut bad = seed_search_law();
    bad.need_rules_hash = "challenge_raw_pipe".to_string();
    assert!(audit_forbidden_inputs(&bad).is_err());
}
