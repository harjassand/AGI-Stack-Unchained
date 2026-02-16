"""Dev evaluation using the suite harness."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from cdel.config import load_config_from_path
from cdel.kernel.parse import parse_definition
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions
from cdel.sealed.config import load_sealed_config
from cdel.sealed.harnesses import get_harness

from orchestrator.types import DevEvalResult


def evaluate_dev(
    *,
    root_dir: Path,
    config_path: Path,
    baseline: str,
    candidate: str,
    oracle: str,
    candidate_payload: dict,
    seed_key: bytes,
    min_diff_sum: int,
    artifact_dir: Path | None = None,
) -> DevEvalResult:
    cfg = load_config_from_path(root_dir, config_path)
    sealed_cfg = load_sealed_config(cfg.data, require_keys=False)
    episodes = _require_episodes(cfg.data)

    eval_cfg = {
        "episodes": episodes,
        "max_steps": int((cfg.data.get("evaluator") or {}).get("step_limit", 100000)),
        "paired_seeds": True,
        "oracle_symbol": oracle,
        "eval_harness_id": sealed_cfg.eval_harness_id,
        "eval_harness_hash": sealed_cfg.eval_harness_hash,
        "eval_suite_hash": sealed_cfg.eval_suite_hash,
    }

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    defs = load_definitions(cfg, conn, [baseline, oracle])
    for defn in candidate_payload.get("definitions", []):
        parsed = parse_definition(defn)
        defs[parsed.name] = parsed

    harness = get_harness(eval_cfg["eval_harness_id"])
    if harness.harness_hash != eval_cfg["eval_harness_hash"]:
        raise ValueError("eval_harness_hash mismatch")

    domain = cfg.data.get("spec") or {}
    int_min = int(domain.get("int_min", -3))
    int_max = int(domain.get("int_max", 3))
    list_max_len = int(domain.get("list_max_len", 4))

    with _temp_env("CDEL_SUITES_DIR", None):
        diffs, baseline_successes, candidate_successes, _ = harness.run_episodes(
            eval_cfg=eval_cfg,
            defs_env=defs,
            baseline_symbol=baseline,
            candidate_symbol=candidate,
            oracle_symbol=oracle,
            seed_key=seed_key,
            project_root=root_dir,
            int_min=int_min,
            int_max=int_max,
            list_max_len=list_max_len,
            fun_symbols=[],
            artifact_dir=artifact_dir,
        )

    diff_sum = sum(diffs)
    return DevEvalResult(
        n=episodes,
        diff_sum=diff_sum,
        baseline_successes=baseline_successes,
        candidate_successes=candidate_successes,
        passes_min_dev_diff_sum=diff_sum >= min_diff_sum,
    )


def _require_episodes(data: dict) -> int:
    sealed = data.get("sealed") or {}
    episodes = sealed.get("episodes")
    if not isinstance(episodes, int) or episodes <= 0:
        raise ValueError("sealed.episodes must be positive int")
    return episodes


@contextmanager
def _temp_env(key: str, value: str | None):
    old = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old
