use std::collections::BTreeMap;
use std::path::Path;

use crate::apfsc::archive::family_scores::FamilyScoreRow;
use crate::apfsc::artifacts::{append_jsonl_atomic, digest_json, read_jsonl};
use crate::apfsc::errors::Result;
use crate::apfsc::macro_lib::{load_or_build_active_registry, save_registry};
use crate::apfsc::types::{
    CoreOp, MacroDef, MacroInductionReceipt, MacroOriginKind, MacroRegistry,
};

pub fn mine_macros(
    root: &Path,
    snapshot_hash: &str,
    protocol_version: &str,
    min_support: u32,
    min_public_gain_bpb: f64,
    min_reduction_ratio: f64,
    max_induced: u32,
) -> Result<(MacroRegistry, Vec<MacroInductionReceipt>)> {
    let mut registry = load_or_build_active_registry(root, snapshot_hash, protocol_version)?;

    let rows: Vec<FamilyScoreRow> =
        read_jsonl(&root.join("archive/family_scores.jsonl")).unwrap_or_default();
    let mut support: BTreeMap<String, Vec<&FamilyScoreRow>> = BTreeMap::new();
    for r in &rows {
        if r.stage != "public_static" {
            continue;
        }
        let key = format!(
            "fragment:{}:{}",
            r.improved_families.first().cloned().unwrap_or_else(|| "none".to_string()),
            r.target_subset_pass
        );
        support.entry(key).or_default().push(r);
    }

    let mut receipts = Vec::new();
    let mut induced_count = 0u32;
    for (fragment_key, entries) in support {
        if induced_count >= max_induced {
            break;
        }
        let support_count = entries.len() as u32;
        let mean_gain = if entries.is_empty() {
            0.0
        } else {
            entries
                .iter()
                .filter_map(|r| r.weighted_static_public_bpb)
                .sum::<f64>()
                / entries.len() as f64
        };
        let op_ratio = 1.0 + (support_count as f64 / 10.0);
        let accepted = support_count >= min_support
            && mean_gain >= min_public_gain_bpb
            && op_ratio >= min_reduction_ratio;
        let macro_id = format!("induced_{}", digest_json(&fragment_key)?);

        let receipt = MacroInductionReceipt {
            macro_id: macro_id.clone(),
            support_count,
            source_fragment_hashes: entries.iter().map(|e| e.replay_hash.clone()).collect(),
            mean_public_gain_bpb: mean_gain,
            op_count_reduction_ratio: op_ratio,
            accepted,
            reason: if accepted {
                "Accepted".to_string()
            } else {
                "ThresholdNotMet".to_string()
            },
        };

        append_jsonl_atomic(
            &root
                .join("macro_registry")
                .join(&registry.registry_id)
                .join("admission_receipts.jsonl"),
            &receipt,
        )?;

        if accepted {
            let mut def = MacroDef {
                macro_id: macro_id.clone(),
                version: 1,
                origin_kind: MacroOriginKind::InducedFromArchive,
                origin_hash: digest_json(&fragment_key)?,
                input_ports: vec![],
                output_ports: vec![],
                local_state_bytes: 32,
                expansion_hash: String::new(),
                expansion_core: vec![CoreOp {
                    op: "ScanReduce".to_string(),
                    args: BTreeMap::new(),
                }],
                max_expansion_ops: crate::apfsc::constants::MAX_MACRO_EXPANSION_OPS,
                canonical_hash: String::new(),
            };
            def.expansion_hash = digest_json(&def.expansion_core)?;
            def.canonical_hash = digest_json(&(def.macro_id.clone(), def.expansion_hash.clone()))?;
            registry.macro_defs.push(def.clone());
            append_jsonl_atomic(
                &root
                    .join("macro_registry")
                    .join(&registry.registry_id)
                    .join("induced_macros.jsonl"),
                &def,
            )?;
            induced_count += 1;
        }

        receipts.push(receipt);
    }

    registry.macro_defs.sort_by(|a, b| a.macro_id.cmp(&b.macro_id));
    registry.manifest_hash = digest_json(&registry)?;
    save_registry(root, &registry)?;
    crate::apfsc::artifacts::write_pointer(root, "active_macro_registry", &registry.registry_id)?;

    Ok((registry, receipts))
}
