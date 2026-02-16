use crate::brain::context::BrainCandidate;

fn seeded_rank(seed_u64: u64, campaign_id: &str, capability_id: &str) -> String {
    use crate::hash;
    let raw = format!("{seed_u64}:{campaign_id}:{capability_id}");
    let sig = hash::sha256_bytes(raw.as_bytes()).unwrap_or_else(|_| "sha256:ff".to_string());
    sig.trim_start_matches("sha256:").to_string()
}

pub fn stable_sort_candidates(
    candidates: &[BrainCandidate],
    seed_u64: u64,
    tie_break_rule: &str,
) -> Vec<BrainCandidate> {
    let mut out = candidates.to_vec();
    out.sort_by(|a, b| {
        b.priority_i32
            .cmp(&a.priority_i32)
            .then_with(|| a.last_run_tick_u64.cmp(&b.last_run_tick_u64))
            .then_with(|| a.estimated_cost_u64.cmp(&b.estimated_cost_u64))
            .then_with(|| {
                if tie_break_rule == "LOWEST_CAMPAIGN_ID" {
                    a.campaign_id
                        .cmp(&b.campaign_id)
                        .then_with(|| a.capability_id.cmp(&b.capability_id))
                } else {
                    seeded_rank(seed_u64, &a.campaign_id, &a.capability_id)
                        .cmp(&seeded_rank(seed_u64, &b.campaign_id, &b.capability_id))
                        .then_with(|| a.campaign_id.cmp(&b.campaign_id))
                        .then_with(|| a.capability_id.cmp(&b.capability_id))
                }
            })
    });
    out
}
