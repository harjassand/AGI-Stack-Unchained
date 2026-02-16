"""Suite-scale solve runner for Track B tasks."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from blake3 import blake3

from cdel.adoption.storage import init_storage as init_adoption_storage
from cdel.bench.taxonomy import all_concepts
from cdel.config import Config
from cdel.ledger import index as idx
from cdel.ledger.closure import compute_closure_with_stats
from cdel.ledger.storage import init_storage, read_head
from cdel.sealed.canon import canon_bytes
from cdel.solve import solve_task


@dataclass(frozen=True)
class SolveSuiteConfig:
    suite: str
    limit: int
    max_candidates: int
    episodes: int
    seed_key: str
    budget_per_task: int
    max_context_symbols: int
    strategy: str
    distractor_modules: int = 0
    distractor_symbols_per_module: int = 0


def run_solve_suite(out_dir: Path, cfg: Config, suite_cfg: SolveSuiteConfig, private_key: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks_dir = out_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    init_storage(cfg)
    init_adoption_storage(cfg)
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)

    tasks = _tasks_for_suite(suite_cfg.suite, suite_cfg.limit)
    total_budget = suite_cfg.budget_per_task * len(tasks)
    idx.set_budget(conn, total_budget)
    conn.commit()

    results = {
        "schema_version": 1,
        "meta": _meta_info(cfg),
        "config": {
            "suite": suite_cfg.suite,
            "limit": suite_cfg.limit,
            "max_candidates": suite_cfg.max_candidates,
            "episodes": suite_cfg.episodes,
            "seed_key": suite_cfg.seed_key,
            "budget_per_task": suite_cfg.budget_per_task,
            "budget_total": total_budget,
            "max_context_symbols": suite_cfg.max_context_symbols,
            "strategy": suite_cfg.strategy,
            "distractor_modules": suite_cfg.distractor_modules,
            "distractor_symbols_per_module": suite_cfg.distractor_symbols_per_module,
        },
        "tasks": [],
        "stop_reason": None,
        "distractors_committed": 0,
    }

    if suite_cfg.distractor_modules > 0 and suite_cfg.distractor_symbols_per_module > 0:
        results["distractors_committed"] = _seed_distractors(
            cfg, conn, suite_cfg.distractor_modules, suite_cfg.distractor_symbols_per_module
        )

    adopted_symbols: set[str] = set()
    for task_id in tasks:
        report = solve_task(
            cfg,
            task_id,
            max_candidates=suite_cfg.max_candidates,
            episodes=suite_cfg.episodes,
            seed_key=suite_cfg.seed_key,
            private_key=private_key,
            strategy=suite_cfg.strategy,
            max_context_symbols=suite_cfg.max_context_symbols,
        )
        _write_task_log(tasks_dir, task_id, report)
        task_row = _task_row(cfg, conn, report, adopted_symbols)
        results["tasks"].append(task_row)
        if task_row.get("adopted_symbol"):
            adopted_symbols.add(task_row["adopted_symbol"])
        if task_row["capacity_exhausted"]:
            results["stop_reason"] = "capacity_exhausted"
            break

    results["summary"] = _summarize(results, len(tasks))
    _write_outputs(out_dir, results)
    return results


def _tasks_for_suite(suite: str, limit: int) -> list[str]:
    if suite != "trackA":
        raise ValueError(f"unknown suite: {suite}")
    tasks = all_concepts()
    if limit > 0:
        return tasks[:limit]
    return tasks


def _task_row(cfg: Config, conn, report: dict, adopted_symbols: set[str]) -> dict:
    attempts = report.get("attempts") or []
    accepted_attempt = next((item for item in attempts if item.get("accepted")), None)
    last_attempt = attempts[-1] if attempts else {}
    capacity_exhausted = any(item.get("rejection") == "CAPACITY_EXCEEDED" for item in attempts)
    declared_deps = accepted_attempt.get("declared_deps") if accepted_attempt else None
    reuse = False
    closure_symbols = None
    if accepted_attempt and declared_deps:
        reuse = any(dep in adopted_symbols for dep in declared_deps)
        try:
            closure_symbols, _ = compute_closure_with_stats(conn, [accepted_attempt.get("symbol")])
            closure_symbols = len(closure_symbols)
        except Exception:
            closure_symbols = None
    concept_candidates = None
    concept = report.get("concept")
    if isinstance(concept, str):
        try:
            concept_candidates = len(idx.list_symbols_for_concept(conn, concept, 10_000))
        except Exception:
            concept_candidates = None
    return {
        "task_id": report.get("task_id"),
        "concept": report.get("concept"),
        "family": report.get("family"),
        "strategy": report.get("strategy"),
        "accepted": bool(accepted_attempt),
        "adopted_symbol": accepted_attempt.get("symbol") if accepted_attempt else None,
        "rejection": last_attempt.get("rejection"),
        "capacity_exhausted": capacity_exhausted,
        "reuse": reuse,
        "declared_deps": declared_deps,
        "closure_symbols": closure_symbols,
        "concept_candidates": concept_candidates,
        "attempts": attempts,
    }


def _summarize(results: dict, total_tasks: int) -> dict:
    tasks = results.get("tasks") or []
    solved = sum(1 for row in tasks if row.get("accepted"))
    rejected = len(tasks) - solved
    reuse_count = sum(1 for row in tasks if row.get("accepted") and row.get("reuse"))
    closures = [row.get("closure_symbols") for row in tasks if row.get("accepted") and row.get("closure_symbols") is not None]
    candidates = [row.get("concept_candidates") for row in tasks if row.get("concept_candidates") is not None]
    concept_counts = {
        row.get("concept"): row.get("concept_candidates")
        for row in tasks
        if row.get("concept") and row.get("concept_candidates") is not None
    }
    total_candidates = sum(concept_counts.values())
    active_count = sum(1 for row in tasks if row.get("adopted_symbol"))
    inactive_count = max(total_candidates - active_count, 0)
    return {
        "processed": len(tasks),
        "total": total_tasks,
        "solved": solved,
        "rejected": rejected,
        "stop_reason": results.get("stop_reason"),
        "reuse_ratio": (reuse_count / solved) if solved else None,
        "avg_closure_symbols": (sum(closures) / len(closures)) if closures else None,
        "avg_concept_candidates": (sum(candidates) / len(candidates)) if candidates else None,
        "candidates_per_concept": _distribution_stats(candidates),
        "closure_symbols_dist": _distribution_stats(closures),
        "active_candidates": active_count,
        "inactive_candidates": inactive_count,
    }


def _write_task_log(tasks_dir: Path, task_id: str, report: dict) -> None:
    safe = task_id.replace("/", "_")
    out_path = tasks_dir / f"{safe}.json"
    out_path.write_text(json.dumps(report, sort_keys=True, indent=2), encoding="utf-8")


def _write_outputs(out_dir: Path, results: dict) -> None:
    results_path = out_dir / "suite_scoreboard.json"
    summary_path = out_dir / "suite_summary.md"
    results_path.write_text(json.dumps(results, sort_keys=True, indent=2), encoding="utf-8")

    summary = results.get("summary") or {}
    lines = [
        "# Solve Suite Summary",
        "",
        f"- processed: {summary.get('processed')}",
        f"- total: {summary.get('total')}",
        f"- solved: {summary.get('solved')}",
        f"- rejected: {summary.get('rejected')}",
        f"- stop_reason: {summary.get('stop_reason')}",
        f"- reuse_ratio: {summary.get('reuse_ratio')}",
        f"- avg_closure_symbols: {summary.get('avg_closure_symbols')}",
        f"- avg_concept_candidates: {summary.get('avg_concept_candidates')}",
        f"- candidates_per_concept: {summary.get('candidates_per_concept')}",
        f"- closure_symbols_dist: {summary.get('closure_symbols_dist')}",
        f"- active_candidates: {summary.get('active_candidates')}",
        f"- inactive_candidates: {summary.get('inactive_candidates')}",
    ]
    summary_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _distribution_stats(values: list[int]) -> dict | None:
    if not values:
        return None
    values = sorted(values)
    return {
        "min": values[0],
        "median": _percentile(values, 50),
        "p95": _percentile(values, 95),
        "max": values[-1],
    }


def _percentile(values: list[int], pct: int) -> int:
    if not values:
        return 0
    if pct <= 0:
        return values[0]
    if pct >= 100:
        return values[-1]
    idx_k = int(((pct / 100) * len(values)) + 0.9999999) - 1
    idx_k = max(0, min(idx_k, len(values) - 1))
    return values[idx_k]


def _meta_info(cfg: Config) -> dict:
    sealed = cfg.data.get("sealed") or {}
    return {
        "git_commit": _git_commit(_repo_root()),
        "config_hash": _config_hash(cfg.data),
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


def _seed_distractors(cfg: Config, conn, modules: int, per_module: int) -> int:
    committed = 0
    for mod_idx in range(modules):
        symbols = [f"distractor_{mod_idx}_{idx}" for idx in range(per_module)]
        definitions = []
        for idx_k, name in enumerate(symbols):
            definitions.append(
                {
                    "name": name,
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "int", "value": idx_k},
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            )
        module = {
            "schema_version": 1,
            "dsl_version": 1,
            "parent": read_head(cfg),
            "payload": {
                "new_symbols": symbols,
                "definitions": definitions,
                "declared_deps": [],
                "specs": [],
                "concepts": [],
            },
        }
        from cdel.ledger.verifier import commit_module

        result = commit_module(cfg, module)
        if not result.ok:
            break
        committed += len(symbols)
    return committed
