use baremetal_lgp::apfsc::challenge_scheduler::score_hidden_challenge_gate;
use baremetal_lgp::apfsc::types::{ChallengeRole, HiddenChallengeFamily, HiddenChallengeManifest};

#[test]
fn hidden_challenge_catastrophic_regression_rejects() {
    let manifest = HiddenChallengeManifest {
        constellation_id: "c".to_string(),
        snapshot_hash: "s".to_string(),
        active_hidden_families: vec![HiddenChallengeFamily {
            family_id: "f_hidden".to_string(),
            role: ChallengeRole::HiddenGeneralization,
            source_pack_hash: "p".to_string(),
            window_commit_hash: "w".to_string(),
            reveal_epoch: 0,
            retire_after_epoch: 8,
            protected: true,
        }],
        retired_hidden_families: vec![],
        manifest_hash: "m".to_string(),
    };

    let mut found = None;
    for i in 0..2000 {
        let cand = format!("cand_{i}");
        let r = score_hidden_challenge_gate(&cand, "inc", &manifest, "v").expect("score");
        if r.catastrophic_regression {
            found = Some(r);
            break;
        }
    }
    let r = found.expect("find catastrophic sample");
    assert!(!r.pass);
    assert!(r.catastrophic_regression);
}
