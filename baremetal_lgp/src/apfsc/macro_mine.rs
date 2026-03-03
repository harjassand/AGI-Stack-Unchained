use std::collections::BTreeMap;
use std::path::Path;

use crate::apfsc::active::read_active_epoch_mode;
use crate::apfsc::archive::family_scores::FamilyScoreRow;
use crate::apfsc::artifacts::{append_jsonl_atomic, digest_json, read_jsonl};
use crate::apfsc::errors::Result;
use crate::apfsc::macro_lib::{load_or_build_active_registry, save_registry};
use crate::apfsc::types::{
    CoreOp, MacroDef, MacroInductionReceipt, MacroOriginKind, MacroRegistry,
};
use crate::oracle3::compile::{synthesize_alien_jit_blob_from_seed, AlienSeedRecord};

const CRYSTALLIZE_MIN_SUPPORT: u32 = 3;
const CRYSTALLIZE_MIN_GAIN_BPB: f64 = 0.0005;
const CRYSTALLIZE_MIN_REDUCTION: f64 = 1.10;

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
    let pioneer_epoch = read_active_epoch_mode(root)
        .map(|mode| mode.eq_ignore_ascii_case("pioneer"))
        .unwrap_or(false);

    let rows: Vec<FamilyScoreRow> =
        read_jsonl(&root.join("archive/family_scores.jsonl")).unwrap_or_default();
    let mut support: BTreeMap<String, Vec<&FamilyScoreRow>> = BTreeMap::new();
    for r in &rows {
        if r.stage != "public_static" {
            continue;
        }
        let key = format!(
            "fragment:{}:{}",
            r.improved_families
                .first()
                .cloned()
                .unwrap_or_else(|| "none".to_string()),
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
            let crystallized = pioneer_epoch
                && support_count >= CRYSTALLIZE_MIN_SUPPORT
                && mean_gain >= CRYSTALLIZE_MIN_GAIN_BPB
                && op_ratio >= CRYSTALLIZE_MIN_REDUCTION;
            let alien_hash = digest_json(&(fragment_key.clone(), support_count, mean_gain))?;
            let mut def = MacroDef {
                macro_id: macro_id.clone(),
                version: 1,
                origin_kind: if crystallized {
                    MacroOriginKind::SubstrateCrystallized
                } else {
                    MacroOriginKind::InducedFromArchive
                },
                origin_hash: digest_json(&fragment_key)?,
                input_ports: vec![],
                output_ports: vec![],
                local_state_bytes: 32,
                expansion_hash: String::new(),
                expansion_core: if crystallized {
                    let mut args = BTreeMap::new();
                    args.insert("seed_hash".to_string(), alien_hash.clone());
                    args.insert("hash".to_string(), alien_hash.clone());
                    args.insert("fused_ops".to_string(), support_count.max(1).to_string());
                    args.insert("ops_added".to_string(), format!("fragment:{fragment_key}"));
                    args.insert("ops_removed".to_string(), "legacy_dense_path".to_string());
                    vec![CoreOp {
                        op: "Alien".to_string(),
                        args,
                    }]
                } else {
                    vec![CoreOp {
                        op: "ScanReduce".to_string(),
                        args: BTreeMap::new(),
                    }]
                },
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
            if crystallized {
                let seed_record = AlienSeedRecord {
                    seed_hash: alien_hash.clone(),
                    ops_added: vec![format!("fragment:{fragment_key}")],
                    ops_removed: vec!["legacy_dense_path".to_string()],
                    fused_ops_hint: support_count.max(1),
                    compile_seed: 0,
                    max_fixpoint_iters: 64,
                    epsilon: 1.0 / 1024.0,
                };
                let blob = synthesize_alien_jit_blob_from_seed(&seed_record);
                let blob_dir = root
                    .join("macro_registry")
                    .join(&registry.registry_id)
                    .join("alien_blobs");
                std::fs::create_dir_all(&blob_dir)
                    .map_err(|e| crate::apfsc::errors::io_err(&blob_dir, e))?;
                crate::apfsc::artifacts::write_json_atomic(
                    &blob_dir.join(format!("{}.json", alien_hash)),
                    &blob,
                )?;
                crate::apfsc::artifacts::write_json_atomic(
                    &blob_dir.join(format!("{}.seed.json", alien_hash)),
                    &seed_record,
                )?;
                crate::apfsc::artifacts::append_jsonl_atomic(
                    &root.join("archives").join("alien_crystallization.jsonl"),
                    &serde_json::json!({
                        "macro_id": def.macro_id,
                        "alien_hash": alien_hash,
                        "seed_hash": seed_record.seed_hash,
                        "blob_hash": blob.blob_hash,
                        "fused_ops": blob.fused_op_count,
                        "max_fixpoint_iters": blob.max_fixpoint_iters,
                        "epsilon": blob.epsilon,
                        "registry_id": registry.registry_id,
                    }),
                )?;
            }
            induced_count += 1;
        }

        receipts.push(receipt);
    }

    registry
        .macro_defs
        .sort_by(|a, b| a.macro_id.cmp(&b.macro_id));
    registry.manifest_hash = digest_json(&registry)?;
    save_registry(root, &registry)?;
    crate::apfsc::artifacts::write_pointer(root, "active_macro_registry", &registry.registry_id)?;

    Ok((registry, receipts))
}
