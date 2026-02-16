"""Rust crate synthesis for SAS-Metasearch v16.0."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _default_crate_dir() -> Path:
    return Path(__file__).resolve().parent / "rust" / "sas_metasearch_rs_v1"


def _source_lockfile() -> Path:
    return Path(__file__).resolve().parents[1] / "v15_1" / "rust" / "agi_kernel_rs_v1" / "Cargo.lock"


def _vendor_source_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "v14_0" / "rust" / "cdel_workmeter_rs_v1" / "vendor"


def _cargo_toml() -> str:
    return """[package]
name = "sas_metasearch_rs_v1"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "sas_metasearch_rs_v1"
path = "src/main.rs"

[dependencies]
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
"""


def _rust_toolchain_toml() -> str:
    return """[toolchain]
channel = "stable"
components = ["rustfmt"]
profile = "minimal"
"""


def _cargo_config_toml() -> str:
    return """[source.crates-io]
replace-with = "vendored-sources"

[source.vendored-sources]
directory = "vendor"
"""


def _io_rs() -> str:
    return """use serde::de::DeserializeOwned;
use serde::Serialize;
use std::env;
use std::fs;
use std::path::PathBuf;

pub struct Args {
    pub prior_path: PathBuf,
    pub out_plan_path: PathBuf,
}

impl Args {
    pub fn parse() -> Result<Self, String> {
        let mut it = env::args().skip(1);
        let mut prior_path: Option<PathBuf> = None;
        let mut out_plan_path: Option<PathBuf> = None;
        while let Some(arg) = it.next() {
            match arg.as_str() {
                "--prior" => {
                    let value = it.next().ok_or_else(|| "missing --prior value".to_string())?;
                    prior_path = Some(PathBuf::from(value));
                }
                "--out_plan" => {
                    let value = it.next().ok_or_else(|| "missing --out_plan value".to_string())?;
                    out_plan_path = Some(PathBuf::from(value));
                }
                _ => return Err(format!("unknown arg: {}", arg)),
            }
        }
        Ok(Args {
            prior_path: prior_path.ok_or_else(|| "missing --prior".to_string())?,
            out_plan_path: out_plan_path.ok_or_else(|| "missing --out_plan".to_string())?,
        })
    }
}

pub fn read_json<T: DeserializeOwned>(path: &PathBuf) -> Result<T, String> {
    let raw = fs::read_to_string(path).map_err(|e| format!("read {} failed: {}", path.display(), e))?;
    serde_json::from_str::<T>(&raw).map_err(|e| format!("parse {} failed: {}", path.display(), e))
}

pub fn write_json<T: Serialize>(path: &PathBuf, value: &T) -> Result<(), String> {
    let raw = serde_json::to_string(value).map_err(|e| format!("serialize failed: {}", e))?;
    fs::write(path, raw + "\\n").map_err(|e| format!("write {} failed: {}", path.display(), e))
}
"""


def _main_rs() -> str:
    return """mod generated;
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
"""


def _generated_rs(prior: dict[str, Any], k_max_dev_evals: int) -> str:
    rows: list[str] = []
    for row in sorted(
        prior.get("hypotheses", []),
        key=lambda r: (str(r.get("theory_kind")), int(r.get("norm_pow_p", 0))),
    ):
        kind = str(row.get("theory_kind"))
        p = int(row.get("norm_pow_p", 0))
        q = int(str(row.get("prob_q32", {}).get("q", "0")))
        if q < 0:
            q = 0
        if q > 0xFFFFFFFF:
            q = 0xFFFFFFFF
        rows.append(
            f"    PriorRow {{ theory_kind: \"{kind}\", norm_pow_p: {p}, weight_q32: {q}u32 }},"
        )
    body = "\n".join(rows)
    return (
        "pub struct PriorRow {\n"
        "    pub theory_kind: &'static str,\n"
        "    pub norm_pow_p: u8,\n"
        "    pub weight_q32: u32,\n"
        "}\n\n"
        f"pub const K_MAX_DEV_EVALS: u64 = {int(k_max_dev_evals)}u64;\n\n"
        "pub const PRIOR_TABLE: &[PriorRow] = &[\n"
        f"{body}\n"
        "];\n"
    )


def _ensure_vendor_link(crate_dir: Path) -> None:
    source = _vendor_source_dir()
    if not source.exists():
        raise RuntimeError("missing vendor source directory")
    vendor = crate_dir / "vendor"
    if vendor.exists():
        return
    try:
        os.symlink(source, vendor, target_is_directory=True)
    except FileExistsError:
        return


def materialize_rust_crate(*, prior: dict[str, Any], k_max_dev_evals: int, crate_dir: Path | None = None) -> Path:
    crate = (crate_dir or _default_crate_dir()).resolve()
    (crate / "src").mkdir(parents=True, exist_ok=True)
    (crate / ".cargo").mkdir(parents=True, exist_ok=True)

    (crate / "Cargo.toml").write_text(_cargo_toml(), encoding="utf-8")
    (crate / "rust-toolchain.toml").write_text(_rust_toolchain_toml(), encoding="utf-8")
    (crate / ".cargo" / "config.toml").write_text(_cargo_config_toml(), encoding="utf-8")
    (crate / ".gitignore").write_text("target\n", encoding="utf-8")

    lock_src = _source_lockfile()
    lock_dst = crate / "Cargo.lock"
    if not lock_dst.exists() and lock_src.exists():
        lock_dst.write_bytes(lock_src.read_bytes())

    (crate / "src" / "io.rs").write_text(_io_rs(), encoding="utf-8")
    (crate / "src" / "main.rs").write_text(_main_rs(), encoding="utf-8")
    (crate / "src" / "generated.rs").write_text(_generated_rs(prior, k_max_dev_evals), encoding="utf-8")

    _ensure_vendor_link(crate)
    return crate


__all__ = ["materialize_rust_crate"]
