use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BrainBucket {
    pub bucket_id: String,
    pub total_u64: u64,
    pub spent_u64: u64,
    pub remaining_u64: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BrainBudgetState {
    pub schema_version: String,
    pub total_budget_u64: u64,
    pub spent_budget_u64: u64,
    pub remaining_budget_u64: u64,
    pub per_bucket: Vec<BrainBucket>,
    pub hard_stop: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BrainCandidate {
    pub campaign_id: String,
    pub capability_id: String,
    pub enabled: bool,
    pub estimated_cost_u64: u64,
    pub priority_i32: i32,
    pub last_run_tick_u64: u64,
    pub cooldown_remaining_u64: u64,
    pub tags: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HistoryChoice {
    pub tick_u64: u64,
    pub campaign_id: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HistoryFailure {
    pub tick_u64: u64,
    pub campaign_id: String,
    pub fail_code: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BrainHistory {
    pub schema_version: String,
    pub current_tick_u64: u64,
    pub source_run_root_rel: String,
    pub recent_choices: Vec<HistoryChoice>,
    pub recent_failures: Vec<HistoryFailure>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BrainPolicy {
    pub schema_version: String,
    pub max_cost_u64: u64,
    pub min_remaining_budget_u64: u64,
    pub tie_break_rule: String,
    pub selection_rules: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BrainContext {
    pub schema_version: String,
    pub case_id: String,
    pub seed_u64: u64,
    pub budget: BrainBudgetState,
    pub candidates: Vec<BrainCandidate>,
    pub history: BrainHistory,
    pub policy: BrainPolicy,
}

impl BrainContext {
    pub fn validate(&self) -> Result<(), String> {
        if self.schema_version != "brain_context_v1" {
            return Err("INVALID:BRAIN_CONTEXT_SCHEMA".to_string());
        }
        if self.case_id.is_empty() {
            return Err("INVALID:BRAIN_CONTEXT".to_string());
        }
        if self.budget.schema_version != "brain_budget_state_v1" {
            return Err("INVALID:BRAIN_CONTEXT_BUDGET_SCHEMA".to_string());
        }
        if self.budget.total_budget_u64 < self.budget.spent_budget_u64 {
            return Err("INVALID:BRAIN_CONTEXT_BUDGET_MATH".to_string());
        }
        if self.budget.remaining_budget_u64
            != (self.budget.total_budget_u64 - self.budget.spent_budget_u64)
        {
            return Err("INVALID:BRAIN_CONTEXT_BUDGET_MATH".to_string());
        }
        if self.candidates.is_empty() {
            return Err("INVALID:BRAIN_CONTEXT_CANDIDATES".to_string());
        }
        if self.history.schema_version != "brain_history_v1" {
            return Err("INVALID:BRAIN_CONTEXT_HISTORY_SCHEMA".to_string());
        }
        if self.policy.schema_version != "brain_policy_v1" {
            return Err("INVALID:BRAIN_CONTEXT_POLICY_SCHEMA".to_string());
        }
        if self.policy.tie_break_rule != "LOWEST_CAMPAIGN_ID"
            && self.policy.tie_break_rule != "SEEDED_HASH_ORDER_V1"
        {
            return Err("INVALID:BRAIN_CONTEXT_POLICY".to_string());
        }
        Ok(())
    }
}
