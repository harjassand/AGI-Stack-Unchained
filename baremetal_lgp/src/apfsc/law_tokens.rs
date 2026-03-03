use std::collections::BTreeMap;
use std::path::Path;

use crate::apfsc::artifacts::{append_jsonl_atomic, digest_json};
use crate::apfsc::errors::Result;
use crate::apfsc::types::{LawArchiveRecord, LawToken};

fn pioneer_mode_active(root: &Path) -> bool {
    crate::apfsc::artifacts::read_pointer(root, "active_epoch_mode")
        .map(|m| m.eq_ignore_ascii_case("pioneer"))
        .unwrap_or(false)
}

pub fn distill_law_tokens(
    records: &[LawArchiveRecord],
    max_tokens: usize,
) -> Result<Vec<LawToken>> {
    let mut grouped: BTreeMap<(String, String, String), Vec<&LawArchiveRecord>> = BTreeMap::new();
    for r in records {
        grouped
            .entry((
                r.morphology_hash.clone(),
                r.source_lane.clone(),
                format!("{:?}", r.promotion_class),
            ))
            .or_default()
            .push(r);
    }

    let mut tokens = Vec::new();
    for ((morph, lane, cls), rs) in grouped {
        if rs.len() < 2 {
            continue;
        }
        let support = rs.len() as u32;
        let sum_yield: i32 = rs.iter().map(|r| r.yield_points).sum();
        let sum_compute: u64 = rs.iter().map(|r| r.compute_units).sum();
        let conditioned_on = BTreeMap::from([
            ("morphology_hash".to_string(), morph.clone()),
            ("lane".to_string(), lane.clone()),
            ("class".to_string(), cls.clone()),
        ]);
        let payload_hash = digest_json(&(morph.clone(), lane.clone(), cls.clone(), support))?;
        let token_id = digest_json(&(payload_hash.clone(), support))?;
        tokens.push(LawToken {
            token_id,
            token_kind: "bucketed_pattern".to_string(),
            support_count: support,
            mean_yield_points: sum_yield as f64 / support as f64,
            mean_compute_units: sum_compute as f64 / support as f64,
            conditioned_on,
            payload_hash,
        });
    }

    tokens.sort_by(|a, b| a.token_id.cmp(&b.token_id));
    tokens.truncate(max_tokens);
    Ok(tokens)
}

pub fn persist_law_tokens(root: &Path, tokens: &[LawToken]) -> Result<()> {
    let (law_archive_path, archives_path) = if pioneer_mode_active(root) {
        (
            root.join("law_archive").join("incubator_tokens.jsonl"),
            root.join("archives").join("incubator_law_tokens.jsonl"),
        )
    } else {
        (
            root.join("law_archive").join("tokens.jsonl"),
            root.join("archives").join("law_tokens.jsonl"),
        )
    };
    for token in tokens {
        append_jsonl_atomic(&law_archive_path, token)?;
    }
    for token in tokens {
        append_jsonl_atomic(&archives_path, token)?;
    }
    Ok(())
}
