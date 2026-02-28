use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use crate::apfsc::artifacts::{
    digest_json, load_snapshot, read_json, read_pointer, write_json_atomic, write_pointer,
};
use crate::apfsc::bank::{build_role_panel_windows, persist_family_bank};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::constants;
use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::ingress::manifest::decode_reality_meta;
use crate::apfsc::types::{
    ConstellationManifest, FamilyBankManifest, FamilyKind, FamilySpec, PackKind, PackManifest,
    PanelKind, RealityRole, SplitKind,
};

#[derive(Debug, Clone)]
struct FamilyPack {
    pack_hash: String,
    kind: FamilyKind,
    role: RealityRole,
}

pub fn build_constellation(
    root: &Path,
    cfg: &Phase1Config,
    snapshot_hash: &str,
    admitted_reality_pack_hashes: &[String],
) -> Result<ConstellationManifest> {
    let reality_hashes = if admitted_reality_pack_hashes.is_empty() {
        let snap = load_snapshot(root, snapshot_hash)?;
        snap.reality_roots
    } else {
        admitted_reality_pack_hashes.to_vec()
    };

    if reality_hashes.is_empty() {
        return Err(ApfscError::Validation(
            "no reality packs available for constellation build".to_string(),
        ));
    }

    let grouped = load_and_group(root, &reality_hashes)?;
    if grouped.len() > constants::MAX_ACTIVE_FAMILIES {
        return Err(ApfscError::Validation(format!(
            "too many families {} > {}",
            grouped.len(),
            constants::MAX_ACTIVE_FAMILIES
        )));
    }

    let mut family_specs = Vec::new();
    for (family_id, packs) in grouped {
        let mut base = Vec::new();
        let mut transfer = Vec::new();
        let mut robust = Vec::new();
        let mut challenge = Vec::new();
        for p in packs {
            match p.role {
                RealityRole::Base => base.push(p),
                RealityRole::Transfer => transfer.push(p),
                RealityRole::Robust => robust.push(p),
                RealityRole::ChallengeStub => challenge.push(p),
            }
        }

        if base.len() != 1 {
            return Err(ApfscError::Validation(format!(
                "MissingFamilyRole: family={family_id} requires exactly one base pack"
            )));
        }
        if transfer.is_empty() {
            return Err(ApfscError::Validation(format!(
                "MissingFamilyRole: family={family_id} missing transfer pack"
            )));
        }
        if robust.is_empty() {
            return Err(ApfscError::Validation(format!(
                "MissingFamilyRole: family={family_id} missing robust pack"
            )));
        }

        let base_pack = base.remove(0);
        let family_kind = base_pack.kind.clone();
        for p in transfer.iter().chain(robust.iter()).chain(challenge.iter()) {
            if p.kind != family_kind {
                return Err(ApfscError::Validation(format!(
                    "family_kind mismatch in family {family_id}"
                )));
            }
        }

        let mut panel_windows: BTreeMap<String, Vec<crate::apfsc::types::WindowRef>> =
            BTreeMap::new();
        for key in [
            PanelKind::Train.as_key(),
            PanelKind::StaticPublic.as_key(),
            PanelKind::StaticHoldout.as_key(),
            PanelKind::Anchor.as_key(),
            PanelKind::Canary.as_key(),
            PanelKind::TransferTrain.as_key(),
            PanelKind::TransferEval.as_key(),
            PanelKind::RobustPublic.as_key(),
            PanelKind::RobustHoldout.as_key(),
            PanelKind::ChallengeStub.as_key(),
        ] {
            panel_windows.entry(key.to_string()).or_default();
        }

        let mut source_pack_hashes = BTreeSet::new();
        let split_base = constants::phase2_base_split_ratios();
        let split_transfer = constants::phase2_transfer_split_ratios();
        let split_robust = constants::phase2_robust_split_ratios();
        let split_challenge = constants::phase2_challenge_stub_split_ratios();

        let base_map = panel_split_map_base();
        let transfer_map = panel_split_map_transfer();
        let robust_map = panel_split_map_robust();
        let challenge_map = panel_split_map_challenge();

        merge_role_windows(
            root,
            &family_id,
            &base_pack,
            &split_base,
            &base_map,
            cfg.bank.window_len,
            cfg.bank.stride,
            &mut panel_windows,
            &mut source_pack_hashes,
        )?;
        for p in &transfer {
            merge_role_windows(
                root,
                &family_id,
                p,
                &split_transfer,
                &transfer_map,
                cfg.bank.window_len,
                cfg.bank.stride,
                &mut panel_windows,
                &mut source_pack_hashes,
            )?;
        }
        for p in &robust {
            merge_role_windows(
                root,
                &family_id,
                p,
                &split_robust,
                &robust_map,
                cfg.bank.window_len,
                cfg.bank.stride,
                &mut panel_windows,
                &mut source_pack_hashes,
            )?;
        }
        for p in &challenge {
            merge_role_windows(
                root,
                &family_id,
                p,
                &split_challenge,
                &challenge_map,
                cfg.bank.window_len,
                cfg.bank.stride,
                &mut panel_windows,
                &mut source_pack_hashes,
            )?;
        }

        for rows in panel_windows.values_mut() {
            rows.sort_by(|a, b| {
                a.seq_hash
                    .cmp(&b.seq_hash)
                    .then_with(|| a.start.cmp(&b.start))
            });
        }

        let mut panel_counts = BTreeMap::new();
        for (k, rows) in &panel_windows {
            panel_counts.insert(k.clone(), rows.len() as u64);
        }

        let mut family_manifest = FamilyBankManifest {
            family_id: family_id.clone(),
            family_kind: family_kind.clone(),
            source_pack_hashes: source_pack_hashes.into_iter().collect(),
            window_len: cfg.bank.window_len,
            stride: cfg.bank.stride,
            panel_counts,
            manifest_hash: String::new(),
        };
        family_manifest.manifest_hash = digest_json(&family_manifest)?;
        persist_family_bank(root, &family_manifest, &panel_windows)?;

        let weights = cfg.phase2.weights.get(&family_id).cloned().ok_or_else(|| {
            ApfscError::Validation(format!("missing phase2 weights for family {family_id}"))
        })?;
        let floors = cfg.phase2.floors.get(&family_id).cloned().ok_or_else(|| {
            ApfscError::Validation(format!("missing phase2 floors for family {family_id}"))
        })?;

        family_specs.push(FamilySpec {
            family_id: family_id.clone(),
            family_kind,
            base_pack_hash: base_pack.pack_hash,
            transfer_pack_hashes: transfer.into_iter().map(|p| p.pack_hash).collect(),
            robust_pack_hashes: robust.into_iter().map(|p| p.pack_hash).collect(),
            challenge_pack_hashes: challenge.into_iter().map(|p| p.pack_hash).collect(),
            weights,
            floors,
            transfer_adapt: cfg.phase2.transfer.clone(),
        });
    }

    family_specs.sort_by(|a, b| a.family_id.cmp(&b.family_id));

    let mut fresh_families = Vec::new();
    for fam in &family_specs {
        if fam.family_id == "event_sparse" || fam.family_id == "formal_alg" {
            fresh_families.push(crate::apfsc::types::FamilyFreshnessMeta {
                family_id: fam.family_id.clone(),
                admitted_epoch: 0,
                fresh_until_epoch: cfg.phase3.fresh_horizon_epochs,
            });
        }
    }
    fresh_families.sort_by(|a, b| a.family_id.cmp(&b.family_id));

    let normalization = cfg.phase2_policy();
    let mut manifest = ConstellationManifest {
        constellation_id: String::new(),
        snapshot_hash: snapshot_hash.to_string(),
        family_specs,
        fresh_families,
        normalization,
        protocol_version: cfg.protocol.version.clone(),
        manifest_hash: String::new(),
    };

    let constellation_seed = digest_json(&(
        manifest.snapshot_hash.clone(),
        manifest.family_specs.clone(),
        manifest.fresh_families.clone(),
        manifest.normalization.clone(),
        manifest.protocol_version.clone(),
    ))?;
    manifest.constellation_id = constellation_seed;
    manifest.manifest_hash = digest_json(&manifest)?;

    let constellations_dir = root.join("constellations");
    std::fs::create_dir_all(&constellations_dir).map_err(|e| io_err(&constellations_dir, e))?;
    write_json_atomic(
        &constellations_dir.join(format!("{}.json", manifest.constellation_id)),
        &manifest,
    )?;
    write_pointer(root, "active_constellation", &manifest.constellation_id)?;
    Ok(manifest)
}

pub fn load_constellation(root: &Path, constellation_id: &str) -> Result<ConstellationManifest> {
    read_json(
        &root
            .join("constellations")
            .join(format!("{}.json", constellation_id)),
    )
}

pub fn load_active_constellation(root: &Path) -> Result<ConstellationManifest> {
    let id = read_pointer(root, "active_constellation")?;
    load_constellation(root, &id)
}

pub fn resolve_constellation(
    root: &Path,
    requested: Option<&str>,
) -> Result<ConstellationManifest> {
    match requested {
        Some(id) => load_constellation(root, id),
        None => load_active_constellation(root),
    }
}

pub fn pack_hashes_from_snapshot(root: &Path, snapshot_hash: &str) -> Result<Vec<String>> {
    let snap = load_snapshot(root, snapshot_hash)?;
    Ok(snap
        .reality_roots
        .into_iter()
        .filter(|h| {
            root.join("packs")
                .join(match PackKind::Reality {
                    PackKind::Reality => "reality",
                    PackKind::Prior => "prior",
                    PackKind::Substrate => "substrate",
                })
                .join(h)
                .join("manifest.json")
                .exists()
        })
        .collect())
}

fn merge_role_windows(
    root: &Path,
    family_id: &str,
    pack: &FamilyPack,
    split_ratios: &BTreeMap<String, f64>,
    split_mapping: &BTreeMap<String, SplitKind>,
    window_len: u32,
    stride: u32,
    panel_windows: &mut BTreeMap<String, Vec<crate::apfsc::types::WindowRef>>,
    source_pack_hashes: &mut BTreeSet<String>,
) -> Result<()> {
    let payload_path = root
        .join("packs")
        .join("reality")
        .join(&pack.pack_hash)
        .join("payload.bin");
    let payload = std::fs::read(&payload_path).map_err(|e| io_err(&payload_path, e))?;

    let part = build_role_panel_windows(
        family_id,
        &pack.pack_hash,
        &payload,
        window_len,
        stride,
        split_ratios,
        split_mapping,
    )?;
    for (k, mut rows) in part {
        panel_windows.entry(k).or_default().append(&mut rows);
    }
    source_pack_hashes.insert(pack.pack_hash.clone());
    Ok(())
}

fn load_and_group(root: &Path, hashes: &[String]) -> Result<BTreeMap<String, Vec<FamilyPack>>> {
    let mut grouped = BTreeMap::<String, Vec<FamilyPack>>::new();
    for hash in hashes {
        let path = root
            .join("packs")
            .join("reality")
            .join(hash)
            .join("manifest.json");
        if !path.exists() {
            return Err(ApfscError::Missing(format!(
                "missing reality manifest for hash {hash}"
            )));
        }
        let manifest: PackManifest = read_json(&path)?;
        let meta = decode_reality_meta(&manifest)?;
        grouped
            .entry(meta.family_id.clone())
            .or_default()
            .push(FamilyPack {
                pack_hash: hash.clone(),
                kind: meta.family_kind,
                role: meta.role,
            });
    }
    for packs in grouped.values_mut() {
        packs.sort_by(|a, b| a.pack_hash.cmp(&b.pack_hash));
    }
    Ok(grouped)
}

fn panel_split_map_base() -> BTreeMap<String, SplitKind> {
    let mut m = BTreeMap::new();
    m.insert("train".to_string(), SplitKind::Train);
    m.insert("static_public".to_string(), SplitKind::Public);
    m.insert("static_holdout".to_string(), SplitKind::Holdout);
    m.insert("anchor".to_string(), SplitKind::Anchor);
    m.insert("canary".to_string(), SplitKind::Canary);
    m
}

fn panel_split_map_transfer() -> BTreeMap<String, SplitKind> {
    let mut m = BTreeMap::new();
    m.insert("transfer_train".to_string(), SplitKind::TransferTrain);
    m.insert("transfer_eval".to_string(), SplitKind::TransferEval);
    m
}

fn panel_split_map_robust() -> BTreeMap<String, SplitKind> {
    let mut m = BTreeMap::new();
    m.insert("robust_public".to_string(), SplitKind::RobustPublic);
    m.insert("robust_holdout".to_string(), SplitKind::RobustHoldout);
    m
}

fn panel_split_map_challenge() -> BTreeMap<String, SplitKind> {
    let mut m = BTreeMap::new();
    m.insert("challenge_stub".to_string(), SplitKind::ChallengeStub);
    m
}
