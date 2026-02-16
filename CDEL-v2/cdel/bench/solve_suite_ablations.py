"""Ablation runner for solve-suite strategies."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from blake3 import blake3

from cdel.bench.solve_suite import SolveSuiteConfig, run_solve_suite
from cdel.bench.taxonomy import all_concepts
from cdel.config import Config, write_config
from cdel.ledger import index as idx
from cdel.ledger.storage import init_storage
from cdel.adoption.storage import init_storage as init_adoption_storage
from cdel.sealed.canon import canon_bytes
from cdel.sealed.crypto import (
    generate_keypair,
    generate_keypair_from_seed,
    key_id_from_public_key,
    public_key_from_private,
)


@dataclass(frozen=True)
class AblationConfig:
    suite: str
    limit: int
    strategies: list[str]
    max_candidates: int
    episodes: int
    seed_key: str
    budget_per_task: int
    max_context_symbols: int
    deterministic: bool = False


def run_solve_suite_ablations(
    out_dir: Path,
    cfg: AblationConfig,
    *,
    private_key: str | None = None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    priv, pub = _resolve_keys(private_key, deterministic=cfg.deterministic)
    key_id = key_id_from_public_key(pub)

    seed_key_used = cfg.seed_key
    if cfg.deterministic:
        seed_key_used = "deterministic-seed"
    results = {
        "schema_version": 1,
        "meta": _meta_info(_base_config(cfg, pub, key_id)),
        "config": {
            "suite": cfg.suite,
            "limit": cfg.limit,
            "strategies": list(cfg.strategies),
            "max_candidates": cfg.max_candidates,
            "episodes": cfg.episodes,
            "seed_key": seed_key_used,
            "budget_per_task": cfg.budget_per_task,
            "max_context_symbols": cfg.max_context_symbols,
            "deterministic": cfg.deterministic,
        },
        "strategies": {},
    }

    for strategy in cfg.strategies:
        strategy_dir = out_dir / strategy
        root = strategy_dir / "root"
        out = strategy_dir / "out"
        root.mkdir(parents=True, exist_ok=True)
        out.mkdir(parents=True, exist_ok=True)

        data = _base_config(cfg, pub, key_id)
        write_config(root, data)
        exp_cfg = Config(root=root, data=data)
        init_storage(exp_cfg)
        init_adoption_storage(exp_cfg)

        seed_key = seed_key_used
        suite_cfg = SolveSuiteConfig(
            suite=cfg.suite,
            limit=cfg.limit,
            max_candidates=cfg.max_candidates,
            episodes=cfg.episodes,
            seed_key=seed_key,
            budget_per_task=cfg.budget_per_task,
            max_context_symbols=cfg.max_context_symbols,
            strategy=strategy,
        )
        start = time.perf_counter()
        report = run_solve_suite(out, exp_cfg, suite_cfg, private_key=priv)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        results["strategies"][strategy] = _strategy_result(exp_cfg, report, elapsed_ms)

    results["summary"] = _summarize(results)
    _write_outputs(out_dir, results)
    return results


def _resolve_keys(private_key: str | None, deterministic: bool) -> tuple[str, str]:
    if private_key:
        pub = public_key_from_private(private_key)
        return private_key, pub
    if deterministic:
        return generate_keypair_from_seed(b"solve-suite-ablations")
    return generate_keypair()


def _base_config(cfg: AblationConfig, pub: str, key_id: str) -> dict:
    tasks_count = cfg.limit if cfg.limit > 0 else len(all_concepts())
    total_budget = cfg.budget_per_task * tasks_count
    return {
        "ledger": {"budget": total_budget},
        "runs": {"base_dir": "runs"},
        "evaluator": {"step_limit": 100_000},
        "spec": {"int_min": -10, "int_max": 10, "list_max_len": 6},
        "cost": {"alpha": 1, "beta": 1, "gamma": 1},
        "sealed": {
            "public_key": pub,
            "key_id": key_id,
            "public_keys": [],
            "prev_public_keys": [],
            "alpha_total": "1e-4",
            "alpha_schedule": {
                "name": "p_series",
                "exponent": 2,
                "coefficient": "0.60792710185402662866",
            },
            "eval_harness_id": "toy-harness-v1",
            "eval_harness_hash": "harness-hash",
            "eval_suite_hash": "suite-hash",
        },
    }


def _strategy_result(cfg: Config, report: dict, elapsed_ms: float) -> dict:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    modules = _modules_count(conn)
    budget_remaining = idx.get_budget(conn)
    stat_state = idx.get_stat_cert_state(conn)
    summary = report.get("summary") or {}
    attempts = [len(row.get("attempts") or []) for row in report.get("tasks") or []]
    return {
        "elapsed_ms": elapsed_ms,
        "modules": modules,
        "budget_remaining": budget_remaining,
        "alpha_round": stat_state[0] if stat_state else None,
        "alpha_spent": stat_state[1] if stat_state else None,
        "summary": summary,
        "median_attempts": _median(attempts),
        "report": report,
    }


def _summarize(results: dict) -> dict:
    summary: dict[str, dict] = {}
    for strategy, payload in (results.get("strategies") or {}).items():
        report_summary = payload.get("summary") or {}
        summary[strategy] = {
            "solved": report_summary.get("solved"),
            "processed": report_summary.get("processed"),
            "solve_rate": _safe_rate(report_summary.get("solved"), report_summary.get("processed")),
            "reuse_ratio": report_summary.get("reuse_ratio"),
            "avg_closure_symbols": report_summary.get("avg_closure_symbols"),
            "avg_concept_candidates": report_summary.get("avg_concept_candidates"),
            "candidates_per_concept": report_summary.get("candidates_per_concept"),
            "closure_symbols_dist": report_summary.get("closure_symbols_dist"),
            "active_candidates": report_summary.get("active_candidates"),
            "inactive_candidates": report_summary.get("inactive_candidates"),
            "median_attempts": payload.get("median_attempts"),
            "elapsed_ms": payload.get("elapsed_ms"),
            "modules": payload.get("modules"),
            "alpha_round": payload.get("alpha_round"),
            "alpha_spent": payload.get("alpha_spent"),
        }
    return summary


def _modules_count(conn) -> int:
    cur = conn.execute("SELECT COUNT(1) FROM modules")
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _median(values: list[int]) -> int | None:
    if not values:
        return None
    values = sorted(values)
    mid = len(values) // 2
    if len(values) % 2 == 1:
        return values[mid]
    return int((values[mid - 1] + values[mid]) / 2)


def _safe_rate(num: int | None, den: int | None) -> float | None:
    if not num or not den:
        return 0.0 if den else None
    return num / den


def _write_outputs(out_dir: Path, results: dict) -> None:
    results_path = out_dir / "ablations_results.json"
    summary_path = out_dir / "ablations_summary.md"
    results_path.write_text(json.dumps(results, sort_keys=True, indent=2), encoding="utf-8")

    lines = ["# Solve Suite Ablations", ""]
    for strategy, row in (results.get("summary") or {}).items():
        lines.append(
            f"- {strategy}: solved={row.get('solved')} processed={row.get('processed')} "
            f"solve_rate={row.get('solve_rate')} median_attempts={row.get('median_attempts')} "
            f"elapsed_ms={row.get('elapsed_ms')} modules={row.get('modules')} "
            f"reuse_ratio={row.get('reuse_ratio')} avg_closure_symbols={row.get('avg_closure_symbols')} "
            f"avg_concept_candidates={row.get('avg_concept_candidates')} "
            f"candidates_per_concept={row.get('candidates_per_concept')} "
            f"closure_symbols_dist={row.get('closure_symbols_dist')} "
            f"active_candidates={row.get('active_candidates')} inactive_candidates={row.get('inactive_candidates')} "
            f"alpha_round={row.get('alpha_round')} alpha_spent={row.get('alpha_spent')}"
        )
    summary_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _meta_info(data: dict) -> dict:
    sealed = data.get("sealed") or {}
    return {
        "git_commit": _git_commit(_repo_root()),
        "config_hash": _config_hash(data),
        "eval_harness_id": sealed.get("eval_harness_id"),
        "eval_harness_hash": sealed.get("eval_harness_hash"),
        "eval_suite_hash": sealed.get("eval_suite_hash"),
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _config_hash(data: dict) -> str:
    payload = json.loads(json.dumps(data))
    sealed = payload.get("sealed")
    if isinstance(sealed, dict):
        sealed.pop("private_key", None)
    return blake3(canon_bytes(payload)).hexdigest()
