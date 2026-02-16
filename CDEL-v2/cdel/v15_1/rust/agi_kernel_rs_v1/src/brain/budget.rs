use super::context::BrainContext;

#[derive(Clone, Debug, PartialEq)]
pub enum BudgetVerdict {
    Ok,
    Insufficient,
    HardStop,
}

pub fn check_hard_stop(ctx: &BrainContext) -> Option<BudgetVerdict> {
    if ctx.budget.hard_stop {
        return Some(BudgetVerdict::HardStop);
    }
    None
}

pub fn check_min_remaining(ctx: &BrainContext) -> Option<BudgetVerdict> {
    if ctx.budget.remaining_budget_u64 < ctx.policy.min_remaining_budget_u64 {
        return Some(BudgetVerdict::Insufficient);
    }
    None
}
