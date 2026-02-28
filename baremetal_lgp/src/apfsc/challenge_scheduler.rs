use std::collections::BTreeSet;
use std::path::Path;

use crate::apfsc::artifacts::{digest_json, list_pack_hashes, read_json, write_json_atomic};
use crate::apfsc::config::Phase1Config;
use crate::apfsc::constellation::load_active_constellation;
use crate::apfsc::errors::{io_err, Result};
use crate::apfsc::ingress::manifest::decode_reality_meta;
use crate::apfsc::types::{
    ChallengeReceipt, ChallengeRole, ConstellationManifest, HiddenChallengeFamily,
    HiddenChallengeManifest, PackKind, PackManifest,
};

pub fn build_hidden_challenge_manifest(
    root: &Path,
    cfg: &Phase1Config,
    constellation: &ConstellationManifest,
    current_epoch: u64,
) -> Result<HiddenChallengeManifest> {
    let mut candidates = Vec::<HiddenChallengeFamily>::new();

    // Prefer explicit challenge packs already attached to families.
    for fam in &constellation.family_specs {
        for p in &fam.challenge_pack_hashes {
            candidates.push(HiddenChallengeFamily {
                family_id: fam.family_id.clone(),
                role: ChallengeRole::HiddenGeneralization,
                source_pack_hash: p.clone(),
                window_commit_hash: digest_json(&(
                    fam.family_id.clone(),
                    p.clone(),
                    current_epoch,
                ))?,
                reveal_epoch: current_epoch,
                retire_after_epoch: current_epoch + cfg.phase4.challenge_retire_after_epochs,
                protected: fam.floors.protected,
            });
        }
    }

    // Fallback: any reality packs marked as challenge-stub by metadata.
    if candidates.is_empty() {
        let hashes = list_pack_hashes(root, PackKind::Reality)?;
        for h in hashes {
            let mpath = root
                .join("packs")
                .join("reality")
                .join(&h)
                .join("manifest.json");
            if !mpath.exists() {
                continue;
            }
            let manifest: PackManifest = read_json(&mpath)?;
            let meta = decode_reality_meta(&manifest)?;
            if !matches!(meta.role, crate::apfsc::types::RealityRole::ChallengeStub) {
                continue;
            }
            candidates.push(HiddenChallengeFamily {
                family_id: meta.family_id,
                role: ChallengeRole::HiddenGeneralization,
                source_pack_hash: h.clone(),
                window_commit_hash: digest_json(&(h.clone(), current_epoch))?,
                reveal_epoch: current_epoch,
                retire_after_epoch: current_epoch + cfg.phase4.challenge_retire_after_epochs,
                protected: false,
            });
        }
    }

    candidates.sort_by(|a, b| {
        a.family_id
            .cmp(&b.family_id)
            .then_with(|| a.source_pack_hash.cmp(&b.source_pack_hash))
    });

    let mut active = Vec::new();
    let mut seen_family = BTreeSet::new();
    for c in candidates {
        if active.len() >= cfg.phase4.max_hidden_challenge_families {
            break;
        }
        if seen_family.insert(c.family_id.clone()) {
            active.push(c);
        }
    }

    let mut manifest = HiddenChallengeManifest {
        constellation_id: constellation.constellation_id.clone(),
        snapshot_hash: constellation.snapshot_hash.clone(),
        active_hidden_families: active,
        retired_hidden_families: Vec::new(),
        manifest_hash: String::new(),
    };
    manifest.manifest_hash = digest_json(&manifest)?;

    persist_hidden_challenge_manifest(root, &manifest)?;
    Ok(manifest)
}

pub fn persist_hidden_challenge_manifest(
    root: &Path,
    manifest: &HiddenChallengeManifest,
) -> Result<()> {
    let dir = root.join("challenges").join(&manifest.manifest_hash);
    std::fs::create_dir_all(&dir).map_err(|e| io_err(&dir, e))?;
    write_json_atomic(&dir.join("hidden_manifest.json"), manifest)?;

    let sdir = root.join("snapshots").join(&manifest.snapshot_hash);
    std::fs::create_dir_all(&sdir).map_err(|e| io_err(&sdir, e))?;
    write_json_atomic(&sdir.join("hidden_challenge_manifest.json"), manifest)?;
    Ok(())
}

pub fn load_hidden_challenge_manifest_for_snapshot(
    root: &Path,
    snapshot_hash: &str,
) -> Result<HiddenChallengeManifest> {
    read_json(
        &root
            .join("snapshots")
            .join(snapshot_hash)
            .join("hidden_challenge_manifest.json"),
    )
}

pub fn load_or_build_hidden_challenge_manifest(
    root: &Path,
    cfg: &Phase1Config,
    current_epoch: u64,
) -> Result<HiddenChallengeManifest> {
    let constellation = load_active_constellation(root)?;
    let p = root
        .join("snapshots")
        .join(&constellation.snapshot_hash)
        .join("hidden_challenge_manifest.json");
    if p.exists() {
        read_json(&p)
    } else {
        build_hidden_challenge_manifest(root, cfg, &constellation, current_epoch)
    }
}

pub fn score_hidden_challenge_gate(
    candidate_hash: &str,
    incumbent_hash: &str,
    manifest: &HiddenChallengeManifest,
    protocol_version: &str,
) -> Result<ChallengeReceipt> {
    if manifest.active_hidden_families.is_empty() {
        return Ok(ChallengeReceipt {
            candidate_hash: candidate_hash.to_string(),
            incumbent_hash: incumbent_hash.to_string(),
            family_bucket_passes: Default::default(),
            aggregate_bucket_score: 0,
            catastrophic_regression: false,
            pass: true,
            reason: "NoHiddenFamilies".to_string(),
            snapshot_hash: manifest.snapshot_hash.clone(),
            constellation_id: manifest.constellation_id.clone(),
            protocol_version: protocol_version.to_string(),
        });
    }

    let mut family_bucket_passes = std::collections::BTreeMap::new();
    let mut score = 0i32;
    let mut catastrophic = false;

    for fam in &manifest.active_hidden_families {
        let h = digest_json(&(
            candidate_hash,
            incumbent_hash,
            &fam.family_id,
            &fam.source_pack_hash,
        ))?;
        let v = (u8::from_str_radix(&h[0..2], 16).unwrap_or(0) % 5) as i32 - 2; // [-2,2]
        let pass = v >= 0 || !fam.protected;
        if fam.protected && v <= -2 {
            catastrophic = true;
        }
        if pass {
            score += v.max(0);
        } else {
            score += v;
        }
        family_bucket_passes.insert(fam.family_id.clone(), pass);
    }

    let pass = !catastrophic && score >= 0 && family_bucket_passes.values().all(|p| *p);
    Ok(ChallengeReceipt {
        candidate_hash: candidate_hash.to_string(),
        incumbent_hash: incumbent_hash.to_string(),
        family_bucket_passes,
        aggregate_bucket_score: score,
        catastrophic_regression: catastrophic,
        pass,
        reason: if pass {
            "ChallengePass".to_string()
        } else if catastrophic {
            "CatastrophicChallengeRegression".to_string()
        } else {
            "ChallengeBucketFail".to_string()
        },
        snapshot_hash: manifest.snapshot_hash.clone(),
        constellation_id: manifest.constellation_id.clone(),
        protocol_version: protocol_version.to_string(),
    })
}

pub fn ensure_hidden_manifest_exists(root: &Path, cfg: &Phase1Config, epoch: u64) -> Result<()> {
    let _ = load_or_build_hidden_challenge_manifest(root, cfg, epoch)?;
    Ok(())
}
