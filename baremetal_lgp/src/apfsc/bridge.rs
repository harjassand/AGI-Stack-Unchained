use std::path::Path;

use crate::apfsc::candidate::CandidateBundle;
use crate::apfsc::constellation::load_constellation;
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::fresh_contact::recent_family_gain;
use crate::apfsc::normalization::evaluate_static_panel;
use crate::apfsc::transfer::evaluate_transfer;
use crate::apfsc::types::{
    BridgePack, BridgeReceipt, ColdBoundaryPack, ConstellationManifest, EvalMode,
    FamilyFreshnessMeta, PanelKind, PromotionClass, RecentFamilyGainReceipt, WarmRefinementPack,
};

pub fn validate_warm_refinement(pack: &WarmRefinementPack) -> Result<()> {
    if pack.protected_families.is_empty() && pack.protected_head_ids.is_empty() {
        return Err(ApfscError::Validation(
            "WarmRefinementPack requires protected_families or protected_head_ids".to_string(),
        ));
    }
    if pack.migration_policy.trim().is_empty() {
        return Err(ApfscError::Validation(
            "WarmRefinementPack.migration_policy must be non-empty".to_string(),
        ));
    }
    if let Some(v) = &pack.observable_map_hash {
        if v.trim().is_empty() {
            return Err(ApfscError::Validation(
                "WarmRefinementPack.observable_map_hash must be non-empty when provided"
                    .to_string(),
            ));
        }
    }
    if let Some(v) = &pack.state_map_hash {
        if v.trim().is_empty() {
            return Err(ApfscError::Validation(
                "WarmRefinementPack.state_map_hash must be non-empty when provided".to_string(),
            ));
        }
    }
    Ok(())
}

pub fn validate_cold_boundary(pack: &ColdBoundaryPack) -> Result<()> {
    if pack.protected_panels.is_empty() {
        return Err(ApfscError::Validation(
            "ColdBoundaryPack.protected_panels must be non-empty".to_string(),
        ));
    }
    if pack.max_error_streak == 0 {
        return Err(ApfscError::Validation(
            "ColdBoundaryPack.max_error_streak must be > 0".to_string(),
        ));
    }
    if pack.mandatory_canary_windows == 0 {
        return Err(ApfscError::Validation(
            "ColdBoundaryPack.mandatory_canary_windows must be > 0".to_string(),
        ));
    }
    if pack.rollback_target_hash.trim().is_empty() {
        return Err(ApfscError::Validation(
            "ColdBoundaryPack.rollback_target_hash must be non-empty".to_string(),
        ));
    }
    Ok(())
}

pub fn evaluate_warm_bridge(
    root: &Path,
    candidate: &CandidateBundle,
    incumbent: &CandidateBundle,
    constellation: &ConstellationManifest,
    pack: &WarmRefinementPack,
) -> Result<BridgeReceipt> {
    validate_warm_refinement(pack)?;

    let anchor_cmp =
        evaluate_static_panel(root, candidate, incumbent, constellation, PanelKind::Anchor)?;
    let pass = anchor_cmp.delta_bpb >= -1e-12 && anchor_cmp.protected_floor_failures.is_empty();
    Ok(BridgeReceipt {
        candidate_hash: candidate.manifest.candidate_hash.clone(),
        incumbent_hash: incumbent.manifest.candidate_hash.clone(),
        promotion_class: candidate.manifest.promotion_class,
        bridge_kind: "Warm".to_string(),
        pass,
        reason: if pass {
            "WarmBridgePass".to_string()
        } else {
            "WarmBridgeFail".to_string()
        },
        anchor_regret_bpb: Some((-anchor_cmp.delta_bpb).max(0.0)),
        max_error_streak: None,
        canary_windows_required: 0,
        snapshot_hash: candidate.manifest.snapshot_hash.clone(),
        constellation_id: constellation.constellation_id.clone(),
        protocol_version: constellation.protocol_version.clone(),
    })
}

pub fn evaluate_cold_boundary(
    root: &Path,
    candidate: &CandidateBundle,
    incumbent: &CandidateBundle,
    constellation: &ConstellationManifest,
    pack: &ColdBoundaryPack,
    freshness: &[FamilyFreshnessMeta],
    current_epoch: u64,
) -> Result<(BridgeReceipt, RecentFamilyGainReceipt)> {
    validate_cold_boundary(pack)?;

    let anchor_cmp =
        evaluate_static_panel(root, candidate, incumbent, constellation, PanelKind::Anchor)?;
    let transfer = evaluate_transfer(root, candidate, incumbent, constellation, EvalMode::Holdout)?;

    let recent = recent_family_gain(
        &candidate.manifest.candidate_hash,
        &incumbent.manifest.candidate_hash,
        &transfer.receipt,
        &anchor_cmp.receipt,
        freshness,
        current_epoch,
        pack.required_recent_family_gain_bpb,
    );

    let anchor_regret_bpb = (-anchor_cmp.delta_bpb).max(0.0);
    let pass = anchor_regret_bpb <= pack.max_anchor_regret_bpb
        && transfer.delta_bpb >= pack.required_transfer_gain_bpb
        && recent.pass;

    Ok((
        BridgeReceipt {
            candidate_hash: candidate.manifest.candidate_hash.clone(),
            incumbent_hash: incumbent.manifest.candidate_hash.clone(),
            promotion_class: PromotionClass::PCold,
            bridge_kind: "Cold".to_string(),
            pass,
            reason: if pass {
                "ColdBoundaryPass".to_string()
            } else {
                "ColdBoundaryFail".to_string()
            },
            anchor_regret_bpb: Some(anchor_regret_bpb),
            max_error_streak: Some(pack.max_error_streak),
            canary_windows_required: pack.mandatory_canary_windows,
            snapshot_hash: candidate.manifest.snapshot_hash.clone(),
            constellation_id: constellation.constellation_id.clone(),
            protocol_version: constellation.protocol_version.clone(),
        },
        recent,
    ))
}

pub fn evaluate_bridge_pack(
    root: &Path,
    candidate: &CandidateBundle,
    incumbent: &CandidateBundle,
    constellation_id: &str,
    pack: &BridgePack,
    freshness: &[FamilyFreshnessMeta],
    current_epoch: u64,
) -> Result<(BridgeReceipt, Option<RecentFamilyGainReceipt>)> {
    let constellation = load_constellation(root, constellation_id)?;
    match pack {
        BridgePack::Warm(w) => Ok((
            evaluate_warm_bridge(root, candidate, incumbent, &constellation, w)?,
            None,
        )),
        BridgePack::Cold(c) => {
            let (bridge, recent) = evaluate_cold_boundary(
                root,
                candidate,
                incumbent,
                &constellation,
                c,
                freshness,
                current_epoch,
            )?;
            Ok((bridge, Some(recent)))
        }
    }
}
