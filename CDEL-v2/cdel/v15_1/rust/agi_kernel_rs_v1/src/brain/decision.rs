use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::{canon, hash};

use super::branch_sig::branch_signature;
use super::budget::{check_hard_stop, check_min_remaining, BudgetVerdict};
use super::context::{BrainCandidate, BrainContext};
use super::policy;
use super::select::stable_sort_candidates;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RuleStep {
    pub rule_id: String,
    pub outcome: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BrainDecision {
    pub schema_version: String,
    pub case_id: String,
    pub verdict: String,
    pub selected_campaign_id: Option<String>,
    pub selected_capability_id: Option<String>,
    pub budget_verdict: String,
    pub rule_path: Vec<RuleStep>,
    pub branch_signature: String,
    pub explain_hash: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BrainDecisionMetrics {
    pub schema_version: String,
    pub case_id: String,
    pub rules_evaluated_u64: u64,
    pub candidates_scanned_u64: u64,
    pub comparisons_u64: u64,
    pub bytes_processed_u64: u64,
    pub candidate_steps_u64: u64,
}

fn budget_to_string(v: &BudgetVerdict) -> String {
    match v {
        BudgetVerdict::Ok => "OK",
        BudgetVerdict::Insufficient => "INSUFFICIENT",
        BudgetVerdict::HardStop => "HARD_STOP",
    }
    .to_string()
}

pub fn brain_decide_with_metrics(
    ctx: &BrainContext,
) -> Result<(BrainDecision, BrainDecisionMetrics), String> {
    ctx.validate()?;

    let mut rule_path: Vec<RuleStep> = Vec::new();
    let mut working: Vec<BrainCandidate> = ctx.candidates.clone();

    let mut budget_verdict = BudgetVerdict::Ok;
    let mut verdict = "SKIP".to_string();
    let mut selected_campaign: Option<String> = None;
    let mut selected_capability: Option<String> = None;

    let max_cost = ctx.policy.max_cost_u64;
    let min_remaining = ctx.policy.min_remaining_budget_u64;
    let remaining = ctx.budget.remaining_budget_u64;

    let bytes_processed_u64 = canon::canonical_bytes(
        &serde_json::to_value(ctx).map_err(|_| "INVALID:SCHEMA_FAIL".to_string())?,
    )?
    .len() as u64;
    let mut rules_evaluated_u64 = 0_u64;
    let mut candidates_scanned_u64 = 0_u64;
    let mut comparisons_u64 = 0_u64;

    for rule in &ctx.policy.selection_rules {
        rules_evaluated_u64 += 1;
        if rule == policy::R0_FILTER_ENABLED {
            let before = working.len();
            candidates_scanned_u64 += before as u64;
            working = working.into_iter().filter(|c| c.enabled).collect();
            rule_path.push(RuleStep {
                rule_id: rule.clone(),
                outcome: format!("kept={};dropped={}", working.len(), before - working.len()),
            });
            continue;
        }

        if rule == policy::R1_FILTER_COOLDOWN {
            let before = working.len();
            candidates_scanned_u64 += before as u64;
            working = working
                .into_iter()
                .filter(|c| c.cooldown_remaining_u64 == 0)
                .collect();
            rule_path.push(RuleStep {
                rule_id: rule.clone(),
                outcome: format!("kept={};dropped={}", working.len(), before - working.len()),
            });
            continue;
        }

        if rule == policy::R2_BUDGET_HARD_STOP {
            if let Some(v) = check_hard_stop(ctx) {
                budget_verdict = v;
                verdict = "STOP".to_string();
                rule_path.push(RuleStep {
                    rule_id: rule.clone(),
                    outcome: "hard_stop=true".to_string(),
                });
                break;
            }
            rule_path.push(RuleStep {
                rule_id: rule.clone(),
                outcome: "hard_stop=false".to_string(),
            });
            continue;
        }

        if rule == policy::R3_BUDGET_MIN_REMAINING {
            if let Some(v) = check_min_remaining(ctx) {
                budget_verdict = v;
                verdict = "STOP".to_string();
                rule_path.push(RuleStep {
                    rule_id: rule.clone(),
                    outcome: format!("remaining={remaining}<min={min_remaining}"),
                });
                break;
            }
            rule_path.push(RuleStep {
                rule_id: rule.clone(),
                outcome: format!("remaining={remaining}>=min={min_remaining}"),
            });
            continue;
        }

        if rule == policy::R4_FILTER_COST_MAX {
            let before = working.len();
            candidates_scanned_u64 += before as u64;
            working = working
                .into_iter()
                .filter(|c| c.estimated_cost_u64 <= max_cost)
                .collect();
            rule_path.push(RuleStep {
                rule_id: rule.clone(),
                outcome: format!("kept={};dropped={}", working.len(), before - working.len()),
            });
            continue;
        }

        if rule == policy::R5_SCORE_PRIORITY {
            let n = working.len() as u64;
            comparisons_u64 += n.saturating_mul(n);
            working = stable_sort_candidates(&working, ctx.seed_u64, &ctx.policy.tie_break_rule);
            let top = if let Some(c) = working.first() {
                c.priority_i32.to_string()
            } else {
                "NONE".to_string()
            };
            rule_path.push(RuleStep {
                rule_id: rule.clone(),
                outcome: format!("top_priority={top}"),
            });
            continue;
        }

        if rule == policy::R6_TIEBREAK {
            comparisons_u64 += 1;
            if let Some(selected) = working.first() {
                selected_campaign = Some(selected.campaign_id.clone());
                selected_capability = Some(selected.capability_id.clone());
                if selected.estimated_cost_u64 > remaining {
                    budget_verdict = BudgetVerdict::Insufficient;
                    verdict = "SKIP".to_string();
                    rule_path.push(RuleStep {
                        rule_id: rule.clone(),
                        outcome: format!(
                            "selected={};cost={};remaining={};budget=insufficient",
                            selected.campaign_id, selected.estimated_cost_u64, remaining
                        ),
                    });
                } else {
                    verdict = "RUN".to_string();
                    rule_path.push(RuleStep {
                        rule_id: rule.clone(),
                        outcome: format!(
                            "selected={};cost={};remaining={};budget=ok",
                            selected.campaign_id, selected.estimated_cost_u64, remaining
                        ),
                    });
                }
            } else {
                rule_path.push(RuleStep {
                    rule_id: rule.clone(),
                    outcome: "no_candidates".to_string(),
                });
            }
            continue;
        }

        rule_path.push(RuleStep {
            rule_id: rule.clone(),
            outcome: "unknown_rule_ignored".to_string(),
        });
    }

    if verdict != "RUN" {
        selected_campaign = None;
        selected_capability = None;
    }

    if verdict == "STOP" && budget_verdict == BudgetVerdict::Ok {
        budget_verdict = BudgetVerdict::Insufficient;
    }

    let branch = branch_signature(&rule_path)?;
    let mut decision = BrainDecision {
        schema_version: "brain_decision_v1".to_string(),
        case_id: ctx.case_id.clone(),
        verdict,
        selected_campaign_id: selected_campaign,
        selected_capability_id: selected_capability,
        budget_verdict: budget_to_string(&budget_verdict),
        rule_path,
        branch_signature: branch,
        explain_hash: String::new(),
    };

    let decision_for_hash = json!({
        "schema_version": decision.schema_version,
        "case_id": decision.case_id,
        "verdict": decision.verdict,
        "selected_campaign_id": decision.selected_campaign_id,
        "selected_capability_id": decision.selected_capability_id,
        "budget_verdict": decision.budget_verdict,
        "rule_path": decision.rule_path,
        "branch_signature": decision.branch_signature,
    });
    let explain_payload = json!({
        "case_id": ctx.case_id,
        "decision": decision_for_hash,
        "candidate_count": ctx.candidates.len(),
    });
    let explain_bytes = canon::canonical_bytes(&explain_payload)?;
    decision.explain_hash = hash::sha256_bytes(&explain_bytes)?;

    let candidate_steps_u64 = rules_evaluated_u64
        .saturating_add(candidates_scanned_u64)
        .saturating_add(comparisons_u64)
        .saturating_add(bytes_processed_u64);
    let metrics = BrainDecisionMetrics {
        schema_version: "brain_perf_case_v1".to_string(),
        case_id: ctx.case_id.clone(),
        rules_evaluated_u64,
        candidates_scanned_u64,
        comparisons_u64,
        bytes_processed_u64,
        candidate_steps_u64,
    };

    Ok((decision, metrics))
}

pub fn brain_decide(ctx: &BrainContext) -> Result<BrainDecision, String> {
    let (decision, _metrics) = brain_decide_with_metrics(ctx)?;
    Ok(decision)
}
