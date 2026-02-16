"""Scoreboard metrics computed from run artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import tomllib


ERROR_KEYS = ("timeout", "security_violation", "runtime_error", "syntax_error", "mem_limit")
ERROR_MAP = {
    "timeout": "timeout",
    "syntax_error": "syntax_error",
    "security_violation": "security_violation",
    "mem_limit": "mem_limit",
    "runtime_error": "runtime_error",
}


def compute_scoreboard(run_dir: Path, *, dev_config: Path, heldout_config: Path) -> dict:
    manifest = _load_json(run_dir / "manifest.json")
    dev_sealed = _load_sealed(dev_config)
    heldout_sealed = _load_sealed(heldout_config)

    dev_evals = _load_dev_evals(run_dir)
    baseline_rate = _baseline_success_rate(dev_evals)
    best_candidate_rate = _best_candidate_success_rate(dev_evals)
    diff_sum_dist = _diff_sum_distribution(dev_evals)
    error_counts = _error_counts(run_dir)
    llm_stats = _llm_stats(manifest)

    return {
        "domain": dev_sealed["eval_harness_id"],
        "run_id": manifest.get("run_id"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dev_suite_hash": dev_sealed["eval_suite_hash"],
        "dev_episodes": dev_sealed["episodes"],
        "heldout_suite_hash": heldout_sealed["eval_suite_hash"],
        "heldout_episodes": heldout_sealed["episodes"],
        "baseline_success_rate": baseline_rate,
        "best_candidate_success_rate": best_candidate_rate,
        "diff_sum_distribution": diff_sum_dist,
        "error_counts": error_counts,
        "heldout_cert_passed": bool(manifest.get("accepted", False)),
        "llm": llm_stats,
    }


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected object in {path}")
    return data


def _load_sealed(config_path: Path) -> dict:
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    sealed = data.get("sealed")
    if not isinstance(sealed, dict):
        raise ValueError(f"sealed config missing in {config_path}")
    required = ("eval_harness_id", "eval_suite_hash", "episodes")
    for key in required:
        if key not in sealed:
            raise ValueError(f"missing sealed field {key} in {config_path}")
    episodes = sealed.get("episodes")
    if not isinstance(episodes, int) or episodes <= 0:
        raise ValueError(f"invalid sealed.episodes in {config_path}")
    return sealed


def _load_dev_evals(run_dir: Path) -> list[dict]:
    dev_evals: list[dict] = []
    for path in sorted(run_dir.glob("candidates/*/dev_eval.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            dev_evals.append(data)
    return dev_evals


def _baseline_success_rate(dev_evals: list[dict]) -> float | None:
    if not dev_evals:
        return None
    baseline = dev_evals[0].get("baseline_successes")
    n = dev_evals[0].get("n")
    if isinstance(baseline, int) and isinstance(n, int) and n > 0:
        return baseline / n
    return None


def _best_candidate_success_rate(dev_evals: list[dict]) -> float | None:
    best = None
    for entry in dev_evals:
        successes = entry.get("candidate_successes")
        n = entry.get("n")
        if isinstance(successes, int) and isinstance(n, int) and n > 0:
            rate = successes / n
            if best is None or rate > best:
                best = rate
    return best


def _diff_sum_distribution(dev_evals: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in dev_evals:
        diff = entry.get("diff_sum")
        if isinstance(diff, int):
            key = str(diff)
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: int(item[0])))


def _error_counts(run_dir: Path) -> dict[str, int]:
    counts = {key: 0 for key in ERROR_KEYS}
    for path in sorted(run_dir.glob("candidates/*/dev_artifacts/*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                continue
            raw_error = row.get("candidate_error")
            if not isinstance(raw_error, str):
                continue
            category = ERROR_MAP.get(raw_error, "runtime_error")
            counts[category] = counts.get(category, 0) + 1
    return counts


def _llm_stats(manifest: dict) -> dict:
    llm_info = manifest.get("llm") or {}
    calls = llm_info.get("calls") or []
    calls_used = llm_info.get("calls_used") or 0
    cache_hits = sum(1 for call in calls if isinstance(call, dict) and call.get("cache_hit") is True)
    cache_hit_rate = (cache_hits / calls_used) if calls_used else 0.0

    attempts = manifest.get("attempts") or []
    retry_counts = [
        entry.get("llm_retry_count")
        for entry in attempts
        if isinstance(entry, dict) and entry.get("llm_retry_count") is not None
    ]
    retries = sum(1 for count in retry_counts if isinstance(count, int) and count > 0)
    retry_rate = (retries / len(retry_counts)) if retry_counts else 0.0

    return {
        "calls_used": calls_used,
        "cache_hit_rate": cache_hit_rate,
        "retry_rate": retry_rate,
    }
