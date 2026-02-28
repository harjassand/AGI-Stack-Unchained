use std::collections::BTreeMap;

use crate::apfsc::types::{
    ConstellationScoreReceipt, FamilyFreshnessMeta, RecentFamilyGainReceipt,
};

pub fn recent_family_gain(
    candidate_hash: &str,
    incumbent_hash: &str,
    transfer_holdout: &ConstellationScoreReceipt,
    static_holdout: &ConstellationScoreReceipt,
    fresh_meta: &[FamilyFreshnessMeta],
    current_epoch: u64,
    tau_recent: f64,
) -> RecentFamilyGainReceipt {
    let mut recent_ids: Vec<String> = fresh_meta
        .iter()
        .filter(|m| current_epoch <= m.fresh_until_epoch)
        .map(|m| m.family_id.clone())
        .collect();
    recent_ids.sort();

    let mut family_gain_bpb = BTreeMap::new();
    let mut max_recent_family_gain_bpb = f64::NEG_INFINITY;

    for fam in &recent_ids {
        let transfer_vec = transfer_holdout.per_family.get(fam);
        let static_vec = static_holdout.per_family.get(fam);

        let gain = if let Some(v) = transfer_vec {
            if let Some(bpb) = v.transfer_holdout_bpb {
                // Candidate score is encoded in receipt; use negative bpb as proxy gain
                -bpb
            } else if let Some(s) = static_vec.and_then(|s| s.static_holdout_bpb) {
                -s
            } else {
                0.0
            }
        } else if let Some(s) = static_vec.and_then(|s| s.static_holdout_bpb) {
            -s
        } else {
            0.0
        };

        family_gain_bpb.insert(fam.clone(), gain);
        if gain > max_recent_family_gain_bpb {
            max_recent_family_gain_bpb = gain;
        }
    }

    if !max_recent_family_gain_bpb.is_finite() {
        max_recent_family_gain_bpb = 0.0;
    }

    RecentFamilyGainReceipt {
        candidate_hash: candidate_hash.to_string(),
        incumbent_hash: incumbent_hash.to_string(),
        recent_family_ids: recent_ids,
        family_gain_bpb,
        max_recent_family_gain_bpb,
        pass: max_recent_family_gain_bpb >= tau_recent,
    }
}
