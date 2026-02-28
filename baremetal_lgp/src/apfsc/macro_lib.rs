use std::path::Path;

use crate::apfsc::artifacts::{digest_json, read_json, write_json_atomic};
use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::types::{CoreOp, MacroDef, MacroOriginKind, MacroRegistry, PortSpec};

pub fn seed_macro_defs() -> Vec<MacroDef> {
    let mut defs = vec![
        seed_macro(
            "EventSparseAccumulator",
            vec!["event", "acc"],
            vec!["acc_out"],
            64,
        ),
        seed_macro("RingDelayTap", vec!["input", "tap"], vec!["output"], 128),
        seed_macro(
            "SelectiveStateCell",
            vec!["state", "mask"],
            vec!["state_out"],
            96,
        ),
        seed_macro(
            "ResetOnDelimiter",
            vec!["byte", "state"],
            vec!["state_out"],
            32,
        ),
    ];
    defs.sort_by(|a, b| a.macro_id.cmp(&b.macro_id));
    defs
}

pub fn build_seed_registry(
    snapshot_hash: &str,
    protocol_version: &str,
    origin_hash: &str,
) -> Result<MacroRegistry> {
    let mut macro_defs = seed_macro_defs();
    for d in &mut macro_defs {
        d.origin_hash = origin_hash.to_string();
        d.expansion_hash = digest_json(&d.expansion_core)?;
        d.canonical_hash = digest_json(&(d.macro_id.clone(), d.expansion_hash.clone()))?;
    }

    let mut registry = MacroRegistry {
        registry_id: String::new(),
        snapshot_hash: snapshot_hash.to_string(),
        macro_defs,
        protocol_version: protocol_version.to_string(),
        manifest_hash: String::new(),
    };
    registry.registry_id =
        digest_json(&(registry.snapshot_hash.clone(), registry.macro_defs.clone()))?;
    registry.manifest_hash = digest_json(&registry)?;
    Ok(registry)
}

pub fn save_registry(root: &Path, registry: &MacroRegistry) -> Result<()> {
    let dir = root.join("macro_registry").join(&registry.registry_id);
    std::fs::create_dir_all(&dir).map_err(|e| io_err(&dir, e))?;
    write_json_atomic(&dir.join("macro_registry.json"), registry)?;
    if !dir.join("induced_macros.jsonl").exists() {
        crate::apfsc::artifacts::write_bytes_atomic(&dir.join("induced_macros.jsonl"), b"")?;
    }
    if !dir.join("admission_receipts.jsonl").exists() {
        crate::apfsc::artifacts::write_bytes_atomic(&dir.join("admission_receipts.jsonl"), b"")?;
    }
    Ok(())
}

pub fn load_registry(root: &Path, registry_id: &str) -> Result<MacroRegistry> {
    let path = root
        .join("macro_registry")
        .join(registry_id)
        .join("macro_registry.json");
    if !path.exists() {
        return Err(ApfscError::Missing(format!(
            "macro registry missing: {}",
            path.display()
        )));
    }
    read_json(&path)
}

pub fn load_or_build_active_registry(
    root: &Path,
    snapshot_hash: &str,
    protocol_version: &str,
) -> Result<MacroRegistry> {
    let pointer = root.join("pointers").join("active_macro_registry");
    if pointer.exists() {
        let id = std::fs::read_to_string(&pointer)
            .map_err(|e| io_err(&pointer, e))?
            .trim()
            .to_string();
        if !id.is_empty() {
            return load_registry(root, &id);
        }
    }

    let registry = build_seed_registry(snapshot_hash, protocol_version, "seed")?;
    save_registry(root, &registry)?;
    crate::apfsc::artifacts::write_pointer(root, "active_macro_registry", &registry.registry_id)?;
    Ok(registry)
}

fn seed_macro(
    name: &str,
    in_ports: Vec<&str>,
    out_ports: Vec<&str>,
    local_state_bytes: u64,
) -> MacroDef {
    let input_ports = in_ports
        .into_iter()
        .map(|n| PortSpec {
            name: n.to_string(),
            width: 1,
        })
        .collect();
    let output_ports = out_ports
        .into_iter()
        .map(|n| PortSpec {
            name: n.to_string(),
            width: 1,
        })
        .collect();
    let expansion_core = vec![
        CoreOp {
            op: "LinearMix".to_string(),
            args: std::collections::BTreeMap::new(),
        },
        CoreOp {
            op: "StateUpdate".to_string(),
            args: std::collections::BTreeMap::new(),
        },
        CoreOp {
            op: "HeadReadout".to_string(),
            args: std::collections::BTreeMap::new(),
        },
    ];
    MacroDef {
        macro_id: name.to_string(),
        version: 1,
        origin_kind: MacroOriginKind::SeedPrior,
        origin_hash: "seed".to_string(),
        input_ports,
        output_ports,
        local_state_bytes,
        expansion_hash: String::new(),
        expansion_core,
        max_expansion_ops: crate::apfsc::constants::MAX_MACRO_EXPANSION_OPS,
        canonical_hash: String::new(),
    }
}
