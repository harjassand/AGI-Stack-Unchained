use std::collections::BTreeMap;
use std::path::Path;

use crate::apfsc::active::{
    read_active_epoch_mode, read_active_incubator_search_law, read_active_search_law,
    write_active_incubator_search_law, write_active_search_law,
};
use crate::apfsc::artifacts::{digest_json, read_json, write_json_atomic};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::Result;
use crate::apfsc::types::{
    LawToken, NeedBucket, NeedToken, SearchLawFeatureVector, SearchLawPack, SearchLawPolicyKind,
    SearchPlan,
};

pub fn seed_search_law() -> SearchLawPack {
    let mut law = SearchLawPack {
        law_id: "searchlaw_seed_v1".to_string(),
        parent_law_hash: None,
        policy_kind: SearchLawPolicyKind::RuleTableV1,
        feature_schema_version: "v1".to_string(),
        lane_weights_q16: BTreeMap::from([
            ("truth".to_string(), 22938),         // ~0.35
            ("equivalence".to_string(), 13107),   // ~0.20
            ("incubator".to_string(), 16384),     // ~0.25
            ("cold_frontier".to_string(), 13107), // ~0.20
        ]),
        class_weights_q16: BTreeMap::from([
            ("S".to_string(), 19661),
            ("A".to_string(), 19661),
            ("PWarm".to_string(), 13107),
            ("PCold".to_string(), 13107),
            ("G".to_string(), 8192),
        ]),
        family_weights_q16: BTreeMap::new(),
        qd_explore_rate_q16: 8192,
        recombination_rate_q16: 4096,
        fresh_family_bias_q16: 8192,
        need_rules_hash: "need_rules_v1".to_string(),
        debt_policy_hash: "debt_policy_v1".to_string(),
        manifest_hash: String::new(),
    };
    law.manifest_hash = digest_json(&law).unwrap_or_else(|_| "searchlaw_seed_v1".to_string());
    law
}

pub fn persist_search_law(root: &Path, law: &SearchLawPack) -> Result<()> {
    let dir = root.join("search_laws").join(&law.manifest_hash);
    std::fs::create_dir_all(&dir).map_err(|e| crate::apfsc::errors::io_err(&dir, e))?;
    write_json_atomic(&dir.join("manifest.json"), law)?;
    write_json_atomic(
        &dir.join("feature_schema.json"),
        &serde_json::json!({
            "version": law.feature_schema_version,
            "policy_kind": format!("{:?}", law.policy_kind),
        }),
    )?;
    write_json_atomic(
        &dir.join("rule_table.json"),
        &serde_json::json!({
            "lane_weights_q16": law.lane_weights_q16,
            "class_weights_q16": law.class_weights_q16,
            "family_weights_q16": law.family_weights_q16,
            "qd_explore_rate_q16": law.qd_explore_rate_q16,
            "recombination_rate_q16": law.recombination_rate_q16,
            "fresh_family_bias_q16": law.fresh_family_bias_q16,
        }),
    )?;
    Ok(())
}

pub fn load_search_law(root: &Path, hash_or_id: &str) -> Result<SearchLawPack> {
    read_json(
        &root
            .join("search_laws")
            .join(hash_or_id)
            .join("manifest.json"),
    )
}

pub fn ensure_active_search_law(root: &Path) -> Result<SearchLawPack> {
    let pioneer = read_active_epoch_mode(root)
        .map(|m| m.eq_ignore_ascii_case("pioneer"))
        .unwrap_or(false);
    let active = if pioneer {
        read_active_incubator_search_law(root)
            .or_else(|_| read_active_search_law(root))
            .unwrap_or_else(|_| "searchlaw_seed_v1".to_string())
    } else {
        read_active_search_law(root).unwrap_or_else(|_| "searchlaw_seed_v1".to_string())
    };
    if let Ok(law) = load_search_law(root, &active) {
        return Ok(law);
    }
    let seed = seed_search_law();
    persist_search_law(root, &seed)?;
    if pioneer {
        write_active_incubator_search_law(root, &seed.manifest_hash)?;
    } else {
        write_active_search_law(root, &seed.manifest_hash)?;
    }
    Ok(seed)
}

fn scaled_u32(v: u32, num: u32, den: u32) -> u32 {
    if den == 0 {
        return v;
    }
    ((v as u64).saturating_mul(num as u64) / den as u64).min(u32::MAX as u64) as u32
}

fn boost_weight(map: &mut BTreeMap<String, u32>, key: &str, delta: u32) {
    map.entry(key.to_string())
        .and_modify(|v| *v = v.saturating_add(delta))
        .or_insert(delta);
}

fn rebalance_q16(weights: &mut BTreeMap<String, u32>) {
    if weights.is_empty() {
        return;
    }
    let total: u64 = weights.values().map(|v| *v as u64).sum();
    if total == 0 {
        return;
    }
    for v in weights.values_mut() {
        *v = ((*v as u64).saturating_mul(65_535) / total).min(65_535) as u32;
    }
}

pub fn generate_search_law_candidates(
    root: &Path,
    active: &SearchLawPack,
    features: &SearchLawFeatureVector,
    law_tokens: &[LawToken],
    cfg: &Phase1Config,
) -> Result<Vec<SearchLawPack>> {
    let mut out = Vec::new();
    let max = cfg.phase4.max_searchlaw_public_candidates.max(1).min(16);

    let mut push = |mut cand: SearchLawPack| -> Result<()> {
        if out.len() >= max {
            return Ok(());
        }
        rebalance_q16(&mut cand.lane_weights_q16);
        rebalance_q16(&mut cand.class_weights_q16);
        cand.manifest_hash = digest_json(&cand)?;
        persist_search_law(root, &cand)?;
        out.push(cand);
        Ok(())
    };

    // Baseline compat mutation: maximize truth pressure while modestly increasing exploration.
    let mut candidate = active.clone();
    candidate.parent_law_hash = Some(active.manifest_hash.clone());
    candidate.law_id = format!("{}_c1", active.law_id);
    candidate
        .lane_weights_q16
        .insert("truth".to_string(), 65_535);
    candidate.recombination_rate_q16 = candidate.recombination_rate_q16.saturating_add(1024);
    candidate.qd_explore_rate_q16 = candidate
        .qd_explore_rate_q16
        .saturating_add((features.underfilled_qd_cells.len() as u32).saturating_mul(64));
    if !law_tokens.is_empty() {
        let t = law_tokens[0].support_count.max(1);
        candidate
            .lane_weights_q16
            .entry("equivalence".to_string())
            .and_modify(|v| *v = scaled_u32(*v, 1 + (t % 3), 1))
            .or_insert(13_107);
    }
    boost_weight(&mut candidate.class_weights_q16, "G", 4096);
    push(candidate)?;

    // Fresh-family pressure mutation.
    let mut c2 = active.clone();
    c2.parent_law_hash = Some(active.manifest_hash.clone());
    c2.law_id = format!("{}_c2", active.law_id);
    c2.fresh_family_bias_q16 = c2.fresh_family_bias_q16.saturating_add(2048);
    c2.debt_policy_hash = "debt_policy_v1_tight".to_string();
    boost_weight(&mut c2.class_weights_q16, "G", 3072);
    push(c2)?;

    // Frontier topology mutations aimed at sparse/event/symbolic discovery.
    let mut hdc_sparse = active.clone();
    hdc_sparse.parent_law_hash = Some(active.manifest_hash.clone());
    hdc_sparse.law_id = format!("{}_hdc_sparse", active.law_id);
    boost_weight(&mut hdc_sparse.lane_weights_q16, "incubator", 4096);
    boost_weight(&mut hdc_sparse.lane_weights_q16, "cold_frontier", 4096);
    boost_weight(&mut hdc_sparse.class_weights_q16, "PWarm", 2048);
    boost_weight(&mut hdc_sparse.class_weights_q16, "PCold", 2048);
    boost_weight(&mut hdc_sparse.class_weights_q16, "G", 8192);
    boost_weight(&mut hdc_sparse.family_weights_q16, "event_sparse", 8192);
    hdc_sparse.need_rules_hash = "need_rules_v2_hdc_sparse".to_string();
    push(hdc_sparse)?;

    let mut symbolic = active.clone();
    symbolic.parent_law_hash = Some(active.manifest_hash.clone());
    symbolic.law_id = format!("{}_symbolic", active.law_id);
    boost_weight(&mut symbolic.lane_weights_q16, "equivalence", 3072);
    boost_weight(&mut symbolic.lane_weights_q16, "cold_frontier", 3072);
    boost_weight(&mut symbolic.class_weights_q16, "PCold", 4096);
    boost_weight(&mut symbolic.class_weights_q16, "G", 8192);
    boost_weight(&mut symbolic.family_weights_q16, "formal_alg", 8192);
    symbolic.need_rules_hash = "need_rules_v2_symbolic".to_string();
    push(symbolic)?;

    let mut mixed = active.clone();
    mixed.parent_law_hash = Some(active.manifest_hash.clone());
    mixed.law_id = format!("{}_hdc_symbolic_mix", active.law_id);
    boost_weight(&mut mixed.lane_weights_q16, "truth", 2048);
    boost_weight(&mut mixed.lane_weights_q16, "incubator", 2048);
    boost_weight(&mut mixed.lane_weights_q16, "cold_frontier", 4096);
    boost_weight(&mut mixed.class_weights_q16, "PWarm", 2048);
    boost_weight(&mut mixed.class_weights_q16, "PCold", 2048);
    boost_weight(&mut mixed.class_weights_q16, "G", 10_240);
    boost_weight(&mut mixed.family_weights_q16, "event_sparse", 6144);
    boost_weight(&mut mixed.family_weights_q16, "formal_alg", 6144);
    mixed.recombination_rate_q16 = mixed.recombination_rate_q16.saturating_add(2048);
    mixed.need_rules_hash = "need_rules_v2_hdc_symbolic_mix".to_string();
    push(mixed)?;

    out.sort_by(|a, b| a.manifest_hash.cmp(&b.manifest_hash));
    out.truncate(max);
    Ok(out)
}

pub fn build_search_plan(
    law: &SearchLawPack,
    features: &SearchLawFeatureVector,
    _law_tokens: &[LawToken],
    epoch_id: u64,
    max_need_tokens: usize,
) -> SearchPlan {
    let mut lane_budget_q16 = law.lane_weights_q16.clone();
    if features.public_plateau_epochs > 1 {
        lane_budget_q16
            .entry("cold_frontier".to_string())
            .and_modify(|v| *v = v.saturating_add(512))
            .or_insert(1024);
    }

    let class_budget_q16 = law.class_weights_q16.clone();
    let family_budget_q16 = law.family_weights_q16.clone();
    let qd_target_cells = features
        .underfilled_qd_cells
        .iter()
        .take(8)
        .cloned()
        .collect::<Vec<_>>();

    let architecture_branch_budgets = vec![
        ("b000".to_string(), 1),
        (
            "b001".to_string(),
            if features.public_plateau_epochs > 0 {
                -1
            } else {
                0
            },
        ),
    ];

    let mut recombination_pairs = Vec::new();
    if features.active_family_ids.len() >= 2 {
        recombination_pairs.push((
            features.active_family_ids[0].clone(),
            features.active_family_ids[1].clone(),
        ));
    }

    let mut need_tokens = Vec::new();
    if features.public_plateau_epochs > 0 {
        let token_id = digest_json(&(
            "plateau_judged_yield",
            law.manifest_hash.clone(),
            epoch_id,
            features.public_plateau_epochs,
        ))
        .unwrap_or_else(|_| format!("need_{}_{}", law.law_id, epoch_id));
        need_tokens.push(NeedToken {
            token_id,
            need_bucket: NeedBucket::Reality,
            priority_q16: 50000,
            requested_family_shape: "fresh_family".to_string(),
            justification_codes: vec!["plateau_judged_yield".to_string()],
            originating_searchlaw_hash: law.manifest_hash.clone(),
            epoch_id,
        });
    }
    if !features.underfilled_qd_cells.is_empty() {
        let token_id = digest_json(&("qd_hole", law.manifest_hash.clone(), epoch_id))
            .unwrap_or_else(|_| format!("need_qd_{}_{}", law.law_id, epoch_id));
        need_tokens.push(NeedToken {
            token_id,
            need_bucket: NeedBucket::Prior,
            priority_q16: 40000,
            requested_family_shape: "morphology_gap".to_string(),
            justification_codes: vec!["qd_hole".to_string()],
            originating_searchlaw_hash: law.manifest_hash.clone(),
            epoch_id,
        });
    }
    need_tokens.sort_by(|a, b| a.token_id.cmp(&b.token_id));
    need_tokens.truncate(max_need_tokens);

    SearchPlan {
        architecture_branch_budgets,
        lane_budget_q16,
        class_budget_q16,
        family_budget_q16,
        qd_target_cells,
        recombination_pairs,
        need_tokens,
    }
}
