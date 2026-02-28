use std::collections::BTreeMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::apfsc::artifacts::{
    digest_bytes, digest_json, read_json, read_jsonl, write_json_atomic,
};
use crate::apfsc::errors::{io_err, ApfscError, Result};
use crate::apfsc::types::{BankManifest, SplitKind, WindowRef};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WindowBank {
    pub manifest: BankManifest,
    pub train: Vec<WindowRef>,
    pub public: Vec<WindowRef>,
    pub holdout: Vec<WindowRef>,
    pub anchor: Vec<WindowRef>,
    pub canary: Vec<WindowRef>,
    pub transfer_train: Vec<WindowRef>,
    pub transfer_eval: Vec<WindowRef>,
}

impl WindowBank {
    pub fn split(&self, split: SplitKind) -> &[WindowRef] {
        match split {
            SplitKind::Train => &self.train,
            SplitKind::Public => &self.public,
            SplitKind::Holdout => &self.holdout,
            SplitKind::Anchor => &self.anchor,
            SplitKind::Canary => &self.canary,
            SplitKind::TransferTrain => &self.transfer_train,
            SplitKind::TransferEval => &self.transfer_eval,
        }
    }
}

pub fn build_bank(
    family_id: &str,
    source_pack_hash: &str,
    payload: &[u8],
    window_len: u32,
    stride: u32,
    split_ratios: &BTreeMap<String, f64>,
) -> Result<WindowBank> {
    if payload.len() < (window_len as usize + 1) {
        return Err(ApfscError::Validation(
            "payload too short for windowing".to_string(),
        ));
    }
    if stride == 0 {
        return Err(ApfscError::Validation("stride must be > 0".to_string()));
    }

    let seq_hash = digest_bytes(payload);
    let mut windows = Vec::new();
    let mut start = 0usize;
    while start + (window_len as usize) < payload.len() {
        windows.push(WindowRef {
            family_id: family_id.to_string(),
            split: SplitKind::Train,
            seq_hash: seq_hash.clone(),
            start: start as u64,
            len: window_len,
            target_offset: window_len,
        });
        start += stride as usize;
    }

    if windows.is_empty() {
        return Err(ApfscError::Validation("no windows generated".to_string()));
    }

    let rotated = rotate_windows(windows, source_pack_hash);
    let counts = split_counts(rotated.len(), split_ratios)?;
    let mut offset = 0usize;

    let train = slice_split(&rotated, &mut offset, counts["train"], SplitKind::Train);
    let public = slice_split(&rotated, &mut offset, counts["public"], SplitKind::Public);
    let holdout = slice_split(&rotated, &mut offset, counts["holdout"], SplitKind::Holdout);
    let anchor = slice_split(&rotated, &mut offset, counts["anchor"], SplitKind::Anchor);
    let canary = slice_split(&rotated, &mut offset, counts["canary"], SplitKind::Canary);
    let transfer_train = slice_split(
        &rotated,
        &mut offset,
        counts["transfer_train"],
        SplitKind::TransferTrain,
    );
    let transfer_eval = slice_split(
        &rotated,
        &mut offset,
        counts["transfer_eval"],
        SplitKind::TransferEval,
    );

    let mut split_counts = BTreeMap::new();
    split_counts.insert("train".to_string(), train.len() as u64);
    split_counts.insert("public".to_string(), public.len() as u64);
    split_counts.insert("holdout".to_string(), holdout.len() as u64);
    split_counts.insert("anchor".to_string(), anchor.len() as u64);
    split_counts.insert("canary".to_string(), canary.len() as u64);
    split_counts.insert("transfer_train".to_string(), transfer_train.len() as u64);
    split_counts.insert("transfer_eval".to_string(), transfer_eval.len() as u64);

    let mut manifest = BankManifest {
        family_id: family_id.to_string(),
        source_pack_hash: source_pack_hash.to_string(),
        window_len,
        stride,
        split_counts,
        manifest_hash: String::new(),
    };
    manifest.manifest_hash = digest_json(&manifest)?;

    Ok(WindowBank {
        manifest,
        train,
        public,
        holdout,
        anchor,
        canary,
        transfer_train,
        transfer_eval,
    })
}

pub fn persist_bank(root: &Path, bank: &WindowBank) -> Result<()> {
    let dir = root.join("banks").join(&bank.manifest.family_id);
    std::fs::create_dir_all(&dir).map_err(|e| io_err(&dir, e))?;

    write_json_atomic(&dir.join("manifest.json"), &bank.manifest)?;
    write_jsonl(&dir.join("train_windows.jsonl"), &bank.train)?;
    write_jsonl(&dir.join("public_windows.jsonl"), &bank.public)?;
    write_jsonl(&dir.join("holdout_windows.jsonl"), &bank.holdout)?;
    write_jsonl(&dir.join("anchor_windows.jsonl"), &bank.anchor)?;
    write_jsonl(&dir.join("canary_windows.jsonl"), &bank.canary)?;
    write_jsonl(
        &dir.join("transfer_train_windows.jsonl"),
        &bank.transfer_train,
    )?;
    write_jsonl(
        &dir.join("transfer_eval_windows.jsonl"),
        &bank.transfer_eval,
    )
}

pub fn load_bank(root: &Path, family_id: &str) -> Result<WindowBank> {
    let dir = root.join("banks").join(family_id);
    let manifest: BankManifest = read_json(&dir.join("manifest.json"))?;
    Ok(WindowBank {
        manifest,
        train: read_jsonl(&dir.join("train_windows.jsonl"))?,
        public: read_jsonl(&dir.join("public_windows.jsonl"))?,
        holdout: read_jsonl(&dir.join("holdout_windows.jsonl"))?,
        anchor: read_jsonl(&dir.join("anchor_windows.jsonl"))?,
        canary: read_jsonl(&dir.join("canary_windows.jsonl"))?,
        transfer_train: read_jsonl(&dir.join("transfer_train_windows.jsonl"))?,
        transfer_eval: read_jsonl(&dir.join("transfer_eval_windows.jsonl"))?,
    })
}

fn rotate_windows(mut windows: Vec<WindowRef>, source_pack_hash: &str) -> Vec<WindowRef> {
    if windows.len() <= 1 {
        return windows;
    }
    let seed = source_pack_hash
        .as_bytes()
        .iter()
        .fold(0u64, |acc, b| acc.wrapping_mul(131).wrapping_add(*b as u64));
    let offset = (seed as usize) % windows.len();
    windows.rotate_left(offset);
    windows
}

fn split_counts(total: usize, ratios: &BTreeMap<String, f64>) -> Result<BTreeMap<String, usize>> {
    let keys = [
        "train",
        "public",
        "holdout",
        "anchor",
        "canary",
        "transfer_train",
        "transfer_eval",
    ];

    let mut counts = BTreeMap::new();
    let mut assigned = 0usize;
    for key in keys {
        let ratio = *ratios
            .get(key)
            .ok_or_else(|| ApfscError::Validation(format!("missing split ratio for {key}")))?;
        if !(0.0..=1.0).contains(&ratio) {
            return Err(ApfscError::Validation(format!(
                "invalid split ratio for {key}"
            )));
        }
        let c = ((total as f64) * ratio).floor() as usize;
        counts.insert(key.to_string(), c);
        assigned += c;
    }

    if assigned < total {
        let mut i = 0usize;
        while assigned < total {
            let key = keys[i % keys.len()];
            *counts.get_mut(key).expect("split key exists") += 1;
            assigned += 1;
            i += 1;
        }
    }
    Ok(counts)
}

fn slice_split(
    windows: &[WindowRef],
    offset: &mut usize,
    count: usize,
    split: SplitKind,
) -> Vec<WindowRef> {
    let end = (*offset + count).min(windows.len());
    let mut out = windows[*offset..end].to_vec();
    for w in &mut out {
        w.split = split;
    }
    *offset = end;
    out
}

fn write_jsonl<T: Serialize>(path: &Path, rows: &[T]) -> Result<()> {
    let mut out = Vec::new();
    for row in rows {
        out.extend(serde_json::to_vec(row)?);
        out.push(b'\n');
    }
    crate::apfsc::artifacts::write_bytes_atomic(path, &out)
}

pub fn window_bytes<'a>(payload: &'a [u8], w: &WindowRef) -> Result<&'a [u8]> {
    let start = w.start as usize;
    let end = start + w.len as usize;
    if end >= payload.len() {
        return Err(ApfscError::Validation("window out of bounds".to_string()));
    }
    Ok(&payload[start..end])
}

pub fn window_target(payload: &[u8], w: &WindowRef) -> Result<u8> {
    let idx = w.start as usize + w.target_offset as usize;
    payload
        .get(idx)
        .copied()
        .ok_or_else(|| ApfscError::Validation("window target out of bounds".to_string()))
}

pub fn load_payload_index(root: &Path) -> Result<BTreeMap<String, Vec<u8>>> {
    let mut out = BTreeMap::new();
    let dir = root.join("packs/reality");
    if !dir.exists() {
        return Ok(out);
    }
    for entry in std::fs::read_dir(&dir).map_err(|e| io_err(&dir, e))? {
        let entry = entry.map_err(|e| io_err(&dir, e))?;
        if !entry
            .file_type()
            .map_err(|e| io_err(entry.path(), e))?
            .is_dir()
        {
            continue;
        }
        let payload_path = entry.path().join("payload.bin");
        if !payload_path.exists() {
            continue;
        }
        let payload = std::fs::read(&payload_path).map_err(|e| io_err(&payload_path, e))?;
        let hash = digest_bytes(&payload);
        out.insert(hash, payload);
    }
    Ok(out)
}

pub fn load_payload_index_for_windows(
    root: &Path,
    windows: &[WindowRef],
) -> Result<BTreeMap<String, Vec<u8>>> {
    let full = load_payload_index(root)?;
    let mut by_seq = BTreeMap::<String, Vec<&WindowRef>>::new();
    for w in windows {
        by_seq.entry(w.seq_hash.clone()).or_default().push(w);
    }

    let mut out = BTreeMap::new();
    for (seq_hash, ws) in by_seq {
        let payload = full.get(&seq_hash).ok_or_else(|| {
            ApfscError::Missing(format!("missing payload for seq_hash {seq_hash}"))
        })?;
        let mut redacted = vec![0u8; payload.len()];
        for w in ws {
            let start = w.start as usize;
            let end = start.saturating_add(w.len as usize);
            if end >= payload.len() {
                continue;
            }
            redacted[start..end].copy_from_slice(&payload[start..end]);
            let t = start.saturating_add(w.target_offset as usize);
            if t < payload.len() {
                redacted[t] = payload[t];
            }
        }
        out.insert(seq_hash, redacted);
    }
    Ok(out)
}
