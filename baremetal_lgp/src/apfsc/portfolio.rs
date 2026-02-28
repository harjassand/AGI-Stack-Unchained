use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use crate::apfsc::artifacts::{digest_json, read_json, write_json_atomic};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::errors::Result;
use crate::apfsc::types::{
    BranchRecord, BranchStatus, PortfolioManifest, PromotionClass, SearchPlan,
};

fn branch_file(root: &Path, portfolio_id: &str) -> std::path::PathBuf {
    root.join("portfolios")
        .join(portfolio_id)
        .join("branches.jsonl")
}

fn debt_file(root: &Path, portfolio_id: &str) -> std::path::PathBuf {
    root.join("portfolios")
        .join(portfolio_id)
        .join("debt_ledger.jsonl")
}

pub fn load_branches(root: &Path, portfolio_id: &str) -> Result<Vec<BranchRecord>> {
    let p = branch_file(root, portfolio_id);
    if !p.exists() {
        return Ok(Vec::new());
    }
    // Stored as JSON array for deterministic rewrite each epoch.
    read_json(&p)
}

pub fn persist_portfolio(
    root: &Path,
    manifest: &PortfolioManifest,
    branches: &[BranchRecord],
) -> Result<()> {
    let pdir = root.join("portfolios").join(&manifest.portfolio_id);
    std::fs::create_dir_all(&pdir).map_err(|e| crate::apfsc::errors::io_err(&pdir, e))?;
    write_json_atomic(&pdir.join("manifest.json"), manifest)?;
    write_json_atomic(&branch_file(root, &manifest.portfolio_id), branches)?;
    Ok(())
}

pub fn load_or_init_portfolio(
    root: &Path,
    snapshot_hash: &str,
    constellation_id: &str,
    active_searchlaw_hash: &str,
    cfg: &Phase1Config,
) -> Result<(PortfolioManifest, Vec<BranchRecord>)> {
    let portfolio_id = format!(
        "portfolio_{}",
        &snapshot_hash[..snapshot_hash.len().min(12)]
    );
    let pdir = root.join("portfolios").join(&portfolio_id);
    let mp = pdir.join("manifest.json");
    if mp.exists() {
        let manifest: PortfolioManifest = read_json(&mp)?;
        let branches = load_branches(root, &portfolio_id)?;
        return Ok((manifest, branches));
    }

    let branch_count = cfg.phase4.max_portfolio_branches.clamp(1, 2);
    let mut branches = Vec::new();
    let mut ids = Vec::new();
    for i in 0..branch_count {
        let bid = format!("b{:03}", i);
        ids.push(bid.clone());
        branches.push(BranchRecord {
            branch_id: bid,
            parent_branch_id: None,
            owner_searchlaw_hash: active_searchlaw_hash.to_string(),
            assigned_lane: "truth".to_string(),
            assigned_family_targets: Vec::new(),
            assigned_class_targets: vec![PromotionClass::S, PromotionClass::A],
            assigned_qd_targets: Vec::new(),
            credit_balance: 0,
            debt_balance: 0,
            idle_epochs: 0,
            status: BranchStatus::Active,
        });
    }
    let manifest = PortfolioManifest {
        portfolio_id,
        snapshot_hash: snapshot_hash.to_string(),
        constellation_id: constellation_id.to_string(),
        active_searchlaw_hash: active_searchlaw_hash.to_string(),
        total_credit_supply: 0,
        total_debt_outstanding: 0,
        branch_ids: ids,
    };
    persist_portfolio(root, &manifest, &branches)?;
    Ok((manifest, branches))
}

fn parse_class_tag(tag: &str) -> Option<PromotionClass> {
    match tag {
        "S" | "s" => Some(PromotionClass::S),
        "A" | "a" => Some(PromotionClass::A),
        "PWarm" | "pwarm" => Some(PromotionClass::PWarm),
        "PCold" | "pcold" => Some(PromotionClass::PCold),
        "G" | "g" => Some(PromotionClass::G),
        _ => None,
    }
}

pub fn allocate_branch_budget(
    root: &Path,
    manifest: &mut PortfolioManifest,
    branches: &mut [BranchRecord],
    plan: &SearchPlan,
    cfg: &Phase1Config,
) -> Result<()> {
    let mut lane_keys: Vec<String> = plan.lane_budget_q16.keys().cloned().collect();
    lane_keys.sort();
    let mut family_keys: Vec<String> = plan.family_budget_q16.keys().cloned().collect();
    family_keys.sort();
    let mut class_keys: Vec<String> = plan.class_budget_q16.keys().cloned().collect();
    class_keys.sort();
    let parsed_classes: Vec<PromotionClass> = class_keys
        .iter()
        .filter_map(|k| parse_class_tag(k))
        .collect();

    let branch_budget_map: BTreeMap<String, i32> =
        plan.architecture_branch_budgets.iter().cloned().collect();

    for (idx, b) in branches.iter_mut().enumerate() {
        if !matches!(
            b.status,
            BranchStatus::Active | BranchStatus::Debt | BranchStatus::Shadow
        ) {
            continue;
        }
        if let Some(lane) = lane_keys.get(idx % lane_keys.len().max(1)) {
            b.assigned_lane = lane.clone();
        }
        b.assigned_family_targets = family_keys
            .iter()
            .skip(idx % family_keys.len().max(1))
            .take(2)
            .cloned()
            .collect();
        if !parsed_classes.is_empty() {
            b.assigned_class_targets = parsed_classes.clone();
        }
        b.assigned_qd_targets = plan
            .qd_target_cells
            .iter()
            .skip(idx % plan.qd_target_cells.len().max(1))
            .take(2)
            .cloned()
            .collect();

        let delta = *branch_budget_map.get(&b.branch_id).unwrap_or(&0);
        if delta >= 0 {
            b.credit_balance += delta;
            b.idle_epochs = 0;
        } else {
            b.debt_balance += -delta;
            b.status = BranchStatus::Debt;
        }
    }

    let mut total_credit = 0i32;
    let mut total_debt = 0i32;
    let mut culled = BTreeSet::new();
    for b in branches.iter_mut() {
        total_credit += b.credit_balance.max(0);
        total_debt += b.debt_balance.max(0);
        if b.debt_balance > cfg.phase4.max_branch_local_debt_credits
            || b.idle_epochs > cfg.phase4.max_idle_epochs_before_cull
        {
            b.status = BranchStatus::Culled;
            culled.insert(b.branch_id.clone());
        }
    }

    manifest.total_credit_supply = total_credit;
    manifest.total_debt_outstanding = total_debt;
    manifest.branch_ids = branches.iter().map(|b| b.branch_id.clone()).collect();

    // Emit deterministic debt ledger snapshot.
    write_json_atomic(&debt_file(root, &manifest.portfolio_id), &branches)?;
    if !culled.is_empty() {
        let receipt = digest_json(&(
            manifest.portfolio_id.clone(),
            culled,
            manifest.total_debt_outstanding,
        ))?;
        crate::apfsc::artifacts::append_jsonl_atomic(
            &root
                .join("portfolios")
                .join(&manifest.portfolio_id)
                .join("cull_receipts.jsonl"),
            &serde_json::json!({
                "receipt_id": receipt,
                "portfolio_id": manifest.portfolio_id,
                "culled": branches.iter().filter(|b| matches!(b.status, BranchStatus::Culled)).map(|b| b.branch_id.clone()).collect::<Vec<_>>(),
            }),
        )?;
    }
    persist_portfolio(root, manifest, branches)?;
    Ok(())
}

pub fn cull_unproductive_branches(
    root: &Path,
    manifest: &mut PortfolioManifest,
    branches: &mut [BranchRecord],
    cfg: &Phase1Config,
) -> Result<Vec<String>> {
    let mut culled = Vec::new();
    for b in branches.iter_mut() {
        if b.debt_balance > cfg.phase4.max_branch_local_debt_credits
            || b.idle_epochs > cfg.phase4.max_idle_epochs_before_cull
        {
            b.status = BranchStatus::Culled;
            culled.push(b.branch_id.clone());
        }
    }
    if !culled.is_empty() {
        crate::apfsc::artifacts::append_jsonl_atomic(
            &root.join("archives/portfolio_trace.jsonl"),
            &serde_json::json!({
                "portfolio_id": manifest.portfolio_id,
                "culled": culled,
            }),
        )?;
    }
    persist_portfolio(root, manifest, branches)?;
    Ok(culled)
}
