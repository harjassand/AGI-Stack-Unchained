mod generated;
mod io;

use generated::{K_MAX_DEV_EVALS, PRIOR_TABLE};
use serde::{Deserialize, Serialize};

#[derive(Deserialize)]
struct Q32In {
    schema_version: String,
    shift: i32,
    q: String,
}

#[derive(Deserialize)]
struct PriorHypothesis {
    theory_kind: String,
    norm_pow_p: u8,
    prob_q32: Q32In,
}

#[derive(Deserialize)]
struct PriorFile {
    schema_version: String,
    hypotheses: Vec<PriorHypothesis>,
}

#[derive(Serialize)]
struct Q32Out {
    schema_version: &'static str,
    shift: i32,
    q: String,
}

#[derive(Serialize)]
struct RankedRow {
    rank_u64: u64,
    theory_kind: String,
    norm_pow_p: u8,
    weight_q32: Q32Out,
    expected_work_cost_u64: u64,
}

#[derive(Serialize)]
struct PlanFile {
    schema_version: &'static str,
    plan_id: String,
    algo_kind: &'static str,
    k_max_dev_evals: u64,
    ranked: Vec<RankedRow>,
}

#[derive(Clone)]
struct RankKey {
    theory_kind: String,
    norm_pow_p: u8,
    weight_q32: u32,
    expected_work_cost_u64: u64,
}

fn expected_work_cost(theory_kind: &str, norm_pow_p: u8) -> u64 {
    let base = if theory_kind == "CANDIDATE_CENTRAL_POWERLAW_V1" { 100u64 } else { 200u64 };
    base + (norm_pow_p as u64 * 10u64)
}

fn lookup_weight(prior: &PriorFile, theory_kind: &str, norm_pow_p: u8) -> Option<u32> {
    for row in prior.hypotheses.iter() {
        if row.theory_kind == theory_kind && row.norm_pow_p == norm_pow_p {
            if row.prob_q32.schema_version != "q32_v1" || row.prob_q32.shift != 32 {
                return None;
            }
            let parsed = row.prob_q32.q.parse::<i64>().ok()?;
            if parsed < 0 || parsed > (u32::MAX as i64) {
                return None;
            }
            return Some(parsed as u32);
        }
    }
    None
}

fn build_ranked(prior: &PriorFile) -> Vec<RankKey> {
    let mut out: Vec<RankKey> = Vec::new();
    for row in PRIOR_TABLE.iter() {
        let weight = lookup_weight(prior, row.theory_kind, row.norm_pow_p).unwrap_or(row.weight_q32);
        out.push(RankKey {
            theory_kind: row.theory_kind.to_string(),
            norm_pow_p: row.norm_pow_p,
            weight_q32: weight,
            expected_work_cost_u64: expected_work_cost(row.theory_kind, row.norm_pow_p),
        });
    }

    out.sort_by(|a, b| {
        b.weight_q32
            .cmp(&a.weight_q32)
            .then_with(|| a.expected_work_cost_u64.cmp(&b.expected_work_cost_u64))
            .then_with(|| a.theory_kind.cmp(&b.theory_kind))
            .then_with(|| a.norm_pow_p.cmp(&b.norm_pow_p))
    });
    out
}

fn main() -> Result<(), String> {
    let args = io::Args::parse()?;
    let prior: PriorFile = io::read_json(&args.prior_path)?;
    if prior.schema_version != "metasearch_prior_v1" {
        return Err("invalid prior schema_version".to_string());
    }

    let ranked = build_ranked(&prior);
    let mut rows: Vec<RankedRow> = Vec::new();
    for (idx, row) in ranked.iter().enumerate() {
        rows.push(RankedRow {
            rank_u64: (idx as u64) + 1,
            theory_kind: row.theory_kind.clone(),
            norm_pow_p: row.norm_pow_p,
            weight_q32: Q32Out {
                schema_version: "q32_v1",
                shift: 32,
                q: row.weight_q32.to_string(),
            },
            expected_work_cost_u64: row.expected_work_cost_u64,
        });
    }

    let plan = PlanFile {
        schema_version: "metasearch_plan_v1",
        plan_id: String::new(),
        algo_kind: "TRACE_PRIOR_V1",
        k_max_dev_evals: K_MAX_DEV_EVALS,
        ranked: rows,
    };

    io::write_json(&args.out_plan_path, &plan)
}
