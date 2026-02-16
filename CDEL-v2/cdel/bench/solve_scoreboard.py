"""Scoreboard runner for Track B solve loop."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from blake3 import blake3

from cdel.adoption.storage import init_storage as init_adoption_storage
from cdel.bench.taxonomy import all_concepts
from cdel.config import Config, write_config
from cdel.ledger import index as idx
from cdel.ledger.storage import init_storage
from cdel.sealed.canon import canon_bytes
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.solve import solve_task


@dataclass(frozen=True)
class ScoreboardConfig:
    tasks: int
    max_candidates: int
    episodes: int
    seed_key: str
    budget: int


def run_solve_scoreboard(out_dir: Path, cfg: ScoreboardConfig) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    priv, pub = generate_keypair()
    key_id = key_id_from_public_key(pub)
    data = _base_config(cfg, pub, key_id)
    concepts = all_concepts()[: cfg.tasks]
    results: dict[str, list[dict]] = {"template_guided": [], "baseline_enum": []}
    for strategy in ("template_guided", "baseline_enum"):
        root = out_dir / strategy
        root.mkdir(parents=True, exist_ok=True)
        exp_cfg = _init_root(root, cfg, data)
        for concept in concepts:
            result = solve_task(
                exp_cfg,
                concept,
                max_candidates=cfg.max_candidates,
                episodes=cfg.episodes,
                seed_key=cfg.seed_key,
                private_key=priv,
                strategy=strategy,
            )
            results[strategy].append(result)

    payload = {
        "meta": _meta_info(Config(root=out_dir, data=data)),
        "config": {
            "tasks": cfg.tasks,
            "max_candidates": cfg.max_candidates,
            "episodes": cfg.episodes,
            "seed_key": cfg.seed_key,
            "budget": cfg.budget,
        },
        "results": results,
    }
    _write_outputs(out_dir, payload)
    return payload


def _init_root(root: Path, cfg: ScoreboardConfig, data: dict) -> Config:
    write_config(root, data)
    exp_cfg = Config(root=root, data=data)
    init_storage(exp_cfg)
    init_adoption_storage(exp_cfg)
    conn = idx.connect(str(exp_cfg.sqlite_path))
    idx.init_schema(conn)
    idx.set_budget(conn, cfg.budget)
    conn.commit()
    return exp_cfg


def _base_config(cfg: ScoreboardConfig, pub: str, key_id: str) -> dict:
    return {
        "ledger": {"budget": cfg.budget},
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


def _write_outputs(out_dir: Path, payload: dict) -> None:
    results_path = out_dir / "trackB_scoreboard.json"
    summary_path = out_dir / "trackB_scoreboard.md"
    results_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")

    lines = ["# Track B Scoreboard", ""]
    for strategy, rows in (payload.get("results") or {}).items():
        total = len(rows)
        accepted = sum(1 for row in rows if _solved(row))
        lines.append(f"- {strategy}: solved={accepted} total={total}")
    summary_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _solved(row: dict) -> bool:
    attempts = row.get("attempts") or []
    return any(attempt.get("accepted") for attempt in attempts)


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
