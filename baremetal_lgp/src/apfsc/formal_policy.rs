use std::collections::BTreeSet;
use std::path::Path;

use crate::apfsc::active::{read_active_formal_policy, write_active_formal_policy};
use crate::apfsc::artifacts::{digest_json, read_json, write_json_atomic};
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::types::{FormalPackAdmissionReceipt, FormalPolicy, FormalRule};

pub fn seed_formal_policy() -> FormalPolicy {
    let mut policy = FormalPolicy {
        policy_id: "formal_policy_seed_v1".to_string(),
        version: 1,
        rules: Vec::new(),
        source_pack_hashes: Vec::new(),
        manifest_hash: String::new(),
    };
    policy.manifest_hash =
        digest_json(&policy).unwrap_or_else(|_| "formal_policy_seed_v1".to_string());
    policy
}

pub fn load_formal_policy(root: &Path, hash_or_id: &str) -> Result<FormalPolicy> {
    let p = root
        .join("formal_policy")
        .join(hash_or_id)
        .join("policy.json");
    read_json(&p)
}

pub fn load_active_formal_policy(root: &Path) -> Result<FormalPolicy> {
    let id =
        read_active_formal_policy(root).unwrap_or_else(|_| "formal_policy_seed_v1".to_string());
    load_formal_policy(root, &id)
}

pub fn persist_formal_policy(root: &Path, policy: &FormalPolicy) -> Result<()> {
    let dir = root.join("formal_policy").join(&policy.manifest_hash);
    std::fs::create_dir_all(&dir).map_err(|e| crate::apfsc::errors::io_err(&dir, e))?;
    write_json_atomic(&dir.join("policy.json"), policy)
}

pub fn is_tightening_only(old_policy: Option<&FormalPolicy>, new_policy: &FormalPolicy) -> bool {
    let Some(old) = old_policy else {
        return true;
    };

    // Tightening-only: keep all existing deny/require rules and optionally add more;
    // no removal and no deny->allow flips.
    let old_ids: BTreeSet<&str> = old.rules.iter().map(|r| r.rule_id.as_str()).collect();
    let new_ids: BTreeSet<&str> = new_policy
        .rules
        .iter()
        .map(|r| r.rule_id.as_str())
        .collect();
    if !old_ids.is_subset(&new_ids) {
        return false;
    }

    for old_rule in &old.rules {
        if let Some(new_rule) = new_policy
            .rules
            .iter()
            .find(|r| r.rule_id == old_rule.rule_id)
        {
            if old_rule.action == "deny" && new_rule.action != "deny" {
                return false;
            }
            if old_rule.action == "require_receipt" && new_rule.action == "allow" {
                return false;
            }
        }
    }

    true
}

pub fn apply_formal_policy(
    root: &Path,
    pack_hash: &str,
    mut policy: FormalPolicy,
    snapshot_hash: &str,
    constellation_id: &str,
    protocol_version: &str,
) -> Result<FormalPackAdmissionReceipt> {
    let old_policy = load_active_formal_policy(root).ok();
    if policy.manifest_hash.is_empty() {
        policy.manifest_hash = digest_json(&policy)?;
    }

    let tightening = is_tightening_only(old_policy.as_ref(), &policy);
    if !tightening {
        return Ok(FormalPackAdmissionReceipt {
            pack_hash: pack_hash.to_string(),
            policy_hash: policy.manifest_hash,
            validated: false,
            tightened_rules_only: false,
            applied: false,
            reason: "FormalPolicyNotTightening".to_string(),
            snapshot_hash: snapshot_hash.to_string(),
            constellation_id: constellation_id.to_string(),
            protocol_version: protocol_version.to_string(),
        });
    }

    persist_formal_policy(root, &policy)?;
    write_active_formal_policy(root, &policy.manifest_hash)?;

    Ok(FormalPackAdmissionReceipt {
        pack_hash: pack_hash.to_string(),
        policy_hash: policy.manifest_hash,
        validated: true,
        tightened_rules_only: true,
        applied: true,
        reason: "Applied".to_string(),
        snapshot_hash: snapshot_hash.to_string(),
        constellation_id: constellation_id.to_string(),
        protocol_version: protocol_version.to_string(),
    })
}

pub fn deny_rule_matches_op(rule: &FormalRule, op_name: &str) -> bool {
    // Phase 4 MVP: `pattern_hash` is treated as deterministic literal op key.
    rule.action == "deny" && rule.pattern_hash == op_name
}

pub fn enforce_formal_policy_on_ops(policy: &FormalPolicy, op_names: &[String]) -> Result<()> {
    for op in op_names {
        for rule in &policy.rules {
            if deny_rule_matches_op(rule, op) {
                return Err(ApfscError::Validation(format!(
                    "formal deny rule '{}' matched op '{}'",
                    rule.rule_id, op
                )));
            }
        }
    }
    Ok(())
}
