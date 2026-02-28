use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::apfsc::bank::{window_bytes, window_target};
use crate::apfsc::emission::{bits_for_target, emit_freq_u16};
use crate::apfsc::errors::{ApfscError, Result};
use crate::apfsc::headpack::apply_linear;
use crate::apfsc::scir::ast::ScirProgram;
use crate::apfsc::scir::interp::run_program;
use crate::apfsc::types::{HeadPack, WindowRef};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ScoreSummary {
    pub family_scores_bits: BTreeMap<String, f64>,
    pub total_bits: f64,
    pub mean_bits_per_byte: f64,
    pub replay_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WindowScore {
    pub start: u64,
    pub target: u8,
    pub bits: f64,
}

pub fn score_panel(
    program: &ScirProgram,
    heads: &HeadPack,
    payloads_by_seq_hash: &BTreeMap<String, Vec<u8>>,
    windows: &[WindowRef],
) -> Result<ScoreSummary> {
    score_panel_with_resid_scales(program, heads, None, payloads_by_seq_hash, windows)
}

pub fn score_panel_with_resid_scales(
    program: &ScirProgram,
    heads: &HeadPack,
    resid_scales: Option<&[f32]>,
    payloads_by_seq_hash: &BTreeMap<String, Vec<u8>>,
    windows: &[WindowRef],
) -> Result<ScoreSummary> {
    if windows.is_empty() {
        return Ok(ScoreSummary {
            family_scores_bits: BTreeMap::new(),
            total_bits: 0.0,
            mean_bits_per_byte: 0.0,
            replay_hash: crate::apfsc::artifacts::digest_bytes(b"empty_panel"),
        });
    }

    let mut family_scores = BTreeMap::<String, f64>::new();
    let mut total_bits = 0.0f64;
    let mut replay_log = Vec::<WindowScore>::with_capacity(windows.len());

    for w in windows {
        let payload = payloads_by_seq_hash.get(&w.seq_hash).ok_or_else(|| {
            ApfscError::Missing(format!("missing payload seq_hash {}", w.seq_hash))
        })?;

        let input = window_bytes(payload, w)?;
        let target = window_target(payload, w)?;
        let interp = run_program(program, input)?;
        let mut adapted = adapt_feature_dim(&interp.feature, heads.native_head.in_dim as usize);
        if let Some(scales) = resid_scales {
            for (i, x) in adapted.iter_mut().enumerate() {
                if i < scales.len() {
                    *x *= 1.0 + scales[i];
                }
            }
        }

        // Force deterministic evaluation order of the native path.
        let _ = apply_linear(&heads.native_head, &adapted);
        let freq = emit_freq_u16(heads, &adapted);
        let bits = bits_for_target(&freq, target);
        total_bits += bits;
        *family_scores.entry(w.family_id.clone()).or_insert(0.0) += bits;
        replay_log.push(WindowScore {
            start: w.start,
            target,
            bits,
        });
    }

    let replay_hash = crate::apfsc::artifacts::digest_json(&replay_log)?;
    Ok(ScoreSummary {
        family_scores_bits: family_scores,
        total_bits,
        mean_bits_per_byte: total_bits / windows.len() as f64,
        replay_hash,
    })
}

fn adapt_feature_dim(feature: &[f32], target_dim: usize) -> Vec<f32> {
    if feature.len() == target_dim {
        return feature.to_vec();
    }
    if feature.len() > target_dim {
        return feature[..target_dim].to_vec();
    }
    let mut out = feature.to_vec();
    out.resize(target_dim, 0.0);
    out
}
