"""Long-horizon solve loop stress runner."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from blake3 import blake3

from cdel.adoption.storage import init_storage as init_adoption_storage
from cdel.bench.taxonomy import all_concepts, concept_family_map
from cdel.ledger.closure import compute_closure_with_stats
from cdel.config import Config, write_config
from cdel.ledger import index as idx
from cdel.ledger.storage import init_storage
from cdel.sealed.canon import canon_bytes
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.solve import solve_task


@dataclass(frozen=True)
class SolveStressConfig:
    tasks: int
    max_candidates: int
    episodes: int
    seed_key: str
    budget: int
    strategy: str
    reuse_every: int = 0


def run_solve_stress(out_dir: Path, cfg: SolveStressConfig) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    root = out_dir / "root"
    root.mkdir(parents=True, exist_ok=True)

    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    data = _base_config(cfg, pub_key, key_id)
    write_config(root, data)
    exp_cfg = Config(root=root, data=data)
    init_storage(exp_cfg)
    init_adoption_storage(exp_cfg)
    conn = idx.connect(str(exp_cfg.sqlite_path))
    idx.init_schema(conn)
    idx.set_budget(conn, cfg.budget)
    conn.commit()

    concepts = all_concepts()
    family_map = concept_family_map()
    reuse_concepts = [c for c in concepts if family_map.get(c) == "reuse"]
    known_hashes = _def_hashes(conn)
    adopted_symbols: set[str] = set()
    accepted_count = 0

    results = {
        "schema_version": 1,
        "meta": _meta_info(exp_cfg),
        "config": {
            "tasks": cfg.tasks,
            "max_candidates": cfg.max_candidates,
            "episodes": cfg.episodes,
            "seed_key": cfg.seed_key,
            "budget": cfg.budget,
            "strategy": cfg.strategy,
            "reuse_every": cfg.reuse_every,
        },
        "steps": [],
        "stop_reason": None,
    }

    for idx_k in range(cfg.tasks):
        if cfg.reuse_every > 0 and reuse_concepts and idx_k % cfg.reuse_every == 0:
            task_id = reuse_concepts[idx_k % len(reuse_concepts)]
        else:
            task_id = concepts[idx_k % len(concepts)]
        report = solve_task(
            exp_cfg,
            task_id,
            max_candidates=cfg.max_candidates,
            episodes=cfg.episodes,
            seed_key=cfg.seed_key,
            private_key=priv_key,
            strategy=cfg.strategy,
        )
        step = _step_row(exp_cfg, conn, idx_k, task_id, report, known_hashes, cfg.budget, adopted_symbols)
        results["steps"].append(step)
        if step.get("accepted"):
            accepted_count += 1
            if step.get("adopted_symbol"):
                adopted_symbols.add(step["adopted_symbol"])
        step["solve_rate"] = accepted_count / (idx_k + 1)
        if step.get("capacity_exhausted"):
            results["stop_reason"] = "capacity_exhausted"
            break
        if step.get("hashes_ok"):
            known_hashes = _def_hashes(conn)

    results["summary"] = _summarize(results, cfg.tasks)
    _write_outputs(out_dir, results)
    return results


def _base_config(cfg: SolveStressConfig, pub_key: str, key_id: str) -> dict:
    return {
        "ledger": {"budget": cfg.budget},
        "runs": {"base_dir": "runs"},
        "evaluator": {"step_limit": 100_000},
        "spec": {"int_min": -10, "int_max": 10, "list_max_len": 6},
        "cost": {"alpha": 1, "beta": 1, "gamma": 1},
        "sealed": {
            "public_key": pub_key,
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


def _step_row(
    cfg: Config,
    conn,
    idx_k: int,
    task_id: str,
    report: dict,
    known_hashes: dict[str, str],
    total_budget: int,
    adopted_symbols: set[str],
) -> dict:
    attempts = report.get("attempts") or []
    accepted = any(item.get("accepted") for item in attempts)
    last_attempt = attempts[-1] if attempts else {}
    capacity_exhausted = any(item.get("rejection") == "CAPACITY_EXCEEDED" for item in attempts)
    alpha = next((item.get("alpha") for item in attempts if item.get("accepted")), None)
    if alpha is None:
        alpha = last_attempt.get("alpha")
    accepted_attempt = next((item for item in attempts if item.get("accepted")), None)
    declared_deps = accepted_attempt.get("declared_deps") if accepted_attempt else None
    reuse = False
    if accepted_attempt and declared_deps:
        reuse = any(dep in adopted_symbols for dep in declared_deps)
    closure_symbols = None
    if accepted_attempt:
        try:
            closure, _ = compute_closure_with_stats(conn, [accepted_attempt.get("symbol")])
            closure_symbols = len(closure)
        except Exception:
            closure_symbols = None
    concept_candidates = None
    concept = report.get("concept")
    if isinstance(concept, str):
        try:
            concept_candidates = len(idx.list_symbols_for_concept(conn, concept, 10_000))
        except Exception:
            concept_candidates = None

    modules_count = _modules_count(conn)
    remaining = idx.get_budget(conn)
    used = total_budget - remaining if remaining is not None else None
    hashes_ok = _hashes_unchanged(conn, known_hashes, sample=10)

    return {
        "task_index": idx_k,
        "task_id": task_id,
        "accepted": accepted,
        "rejection": last_attempt.get("rejection"),
        "adopted_symbol": next((item.get("symbol") for item in attempts if item.get("accepted")), None),
        "capacity_exhausted": capacity_exhausted,
        "reuse": reuse,
        "declared_deps": declared_deps,
        "closure_symbols": closure_symbols,
        "concept_candidates": concept_candidates,
        "alpha": alpha,
        "modules": modules_count,
        "budget_remaining": remaining,
        "budget_used": used,
        "hashes_ok": hashes_ok,
    }


def _summarize(results: dict, total_tasks: int) -> dict:
    steps = results.get("steps") or []
    accepted = sum(1 for row in steps if row.get("accepted"))
    rejected = len(steps) - accepted
    reuse_count = sum(1 for row in steps if row.get("accepted") and row.get("reuse"))
    closures = [row.get("closure_symbols") for row in steps if row.get("accepted") and row.get("closure_symbols") is not None]
    candidates = [row.get("concept_candidates") for row in steps if row.get("concept_candidates") is not None]
    return {
        "processed": len(steps),
        "total": total_tasks,
        "accepted": accepted,
        "rejected": rejected,
        "stop_reason": results.get("stop_reason"),
        "reuse_ratio": (reuse_count / accepted) if accepted else None,
        "avg_closure_symbols": (sum(closures) / len(closures)) if closures else None,
        "candidates_per_concept": _distribution_stats(candidates),
    }


def _write_outputs(out_dir: Path, results: dict) -> None:
    results_path = out_dir / "stress_results.json"
    summary_path = out_dir / "stress_summary.md"
    results_path.write_text(json.dumps(results, sort_keys=True, indent=2), encoding="utf-8")

    summary = results.get("summary") or {}
    lines = [
        "# Solve Stress Summary",
        "",
        f"- processed: {summary.get('processed')}",
        f"- total: {summary.get('total')}",
        f"- accepted: {summary.get('accepted')}",
        f"- rejected: {summary.get('rejected')}",
        f"- stop_reason: {summary.get('stop_reason')}",
        f"- reuse_ratio: {summary.get('reuse_ratio')}",
        f"- avg_closure_symbols: {summary.get('avg_closure_symbols')}",
        f"- candidates_per_concept: {summary.get('candidates_per_concept')}",
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


def _modules_count(conn) -> int:
    cur = conn.execute("SELECT COUNT(1) FROM modules")
    row = cur.fetchone()
    return int(row[0]) if row else 0


def _def_hashes(conn) -> dict[str, str]:
    cur = conn.execute("SELECT symbol, def_hash FROM def_hashes")
    return {row[0]: row[1] for row in cur.fetchall()}


def _hashes_unchanged(conn, known: dict[str, str], sample: int) -> bool:
    if not known:
        return True
    items = sorted(known.items())
    if sample > 0:
        items = items[:sample]
    current = _def_hashes(conn)
    for symbol, def_hash in items:
        if current.get(symbol) != def_hash:
            return False
    return True


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
