use std::collections::BTreeMap;

use baremetal_lgp::apfsc::config::Phase1Config;
use baremetal_lgp::apfsc::credit::mint_credit;
use baremetal_lgp::apfsc::portfolio::{
    allocate_branch_budget, cull_unproductive_branches, load_or_init_portfolio,
};
use baremetal_lgp::apfsc::types::SearchPlan;
use tempfile::tempdir;

#[test]
fn portfolio_credit_and_debt_culling_are_deterministic() {
    let tmp = tempdir().expect("tmp");
    let root = tmp.path().join(".apfsc");
    let mut cfg = Phase1Config::default();
    cfg.phase4.max_portfolio_branches = 2;
    cfg.phase4.max_branch_local_debt_credits = 1;
    cfg.phase4.max_idle_epochs_before_cull = 1;

    let (mut manifest, mut branches) =
        load_or_init_portfolio(&root, "snap", "const", "g", &cfg).expect("portfolio");
    let plan = SearchPlan {
        architecture_branch_budgets: vec![("b000".to_string(), -2), ("b001".to_string(), 1)],
        lane_budget_q16: BTreeMap::from([("truth".to_string(), 1000)]),
        class_budget_q16: BTreeMap::from([("A".to_string(), 1000)]),
        family_budget_q16: BTreeMap::from([("det_micro".to_string(), 1000)]),
        qd_target_cells: vec!["c".to_string()],
        recombination_pairs: vec![],
        need_tokens: vec![],
    };
    allocate_branch_budget(&root, &mut manifest, &mut branches, &plan, &cfg).expect("alloc");
    let _ = mint_credit(
        &root,
        &manifest.portfolio_id,
        "b001",
        2,
        "promote",
        None,
        None,
    )
    .expect("mint");
    for b in &mut branches {
        b.idle_epochs = 2;
    }
    let culled =
        cull_unproductive_branches(&root, &mut manifest, &mut branches, &cfg).expect("cull");
    assert!(!culled.is_empty());
}
