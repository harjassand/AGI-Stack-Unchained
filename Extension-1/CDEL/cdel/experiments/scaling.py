"""Scaling experiment for addressability and lookup performance."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from blake3 import blake3

from cdel.config import Config, load_config, write_default_config
from cdel.kernel.eval import Evaluator
from cdel.kernel.parse import parse_term
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions_scan_with_stats, load_definitions_with_stats
from cdel.ledger.storage import init_storage, read_head
from cdel.ledger.verifier import commit_module
from cdel.sealed.canon import canon_bytes


@dataclass(frozen=True)
class ScalingConfig:
    modules: int
    step: int
    budget: int


def run_scaling_experiment(out_dir: Path, cfg: ScalingConfig) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    root = out_dir / "root"
    root.mkdir(parents=True, exist_ok=True)
    write_default_config(root, cfg.budget)
    exp_cfg = load_config(root)
    init_storage(exp_cfg)
    conn = idx.connect(str(exp_cfg.sqlite_path))
    idx.init_schema(conn)
    idx.set_budget(conn, cfg.budget)
    conn.commit()

    results = {
        "meta": _meta_info(exp_cfg),
        "config": {"modules": cfg.modules, "step": cfg.step, "budget": cfg.budget},
        "measurements": [],
    }

    for i in range(cfg.modules):
        module = _module_for_index(i)
        module["parent"] = read_head(exp_cfg)
        result = commit_module(exp_cfg, module)
        if not result.ok:
            raise ValueError(f"commit failed: {result.rejection}")
        count = i + 1
        if count % cfg.step == 0 or count == cfg.modules:
            results["measurements"].append(_measure(exp_cfg, count))

    _write_outputs(out_dir, results)
    return results


def _module_for_index(idx_k: int) -> dict:
    symbol = f"scale_add_{idx_k}"
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": "GENESIS",
        "payload": {
            "new_symbols": [symbol],
            "definitions": [_int_add_def(symbol, idx_k)],
            "declared_deps": [],
            "specs": [],
            "concepts": [{"concept": "scale.add", "symbol": symbol}],
        },
    }


def _measure(cfg: Config, count: int) -> dict:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    symbol = f"scale_add_{count - 1}"
    term = parse_term(_app_sym(symbol, [_int_lit(5)]), [])

    lookup_ms = _timed_ms(lambda: idx.get_symbol_info(conn, symbol))
    resolve_ms = _timed_ms(lambda: idx.latest_symbol_for_concept(conn, "scale.add"))

    defs, stats = _timed_result(lambda: load_definitions_with_stats(cfg, conn, [symbol], use_cache=False))
    scan_defs, scan_stats = _timed_result(lambda: load_definitions_scan_with_stats(cfg, [symbol]))

    evaluator = Evaluator(int(cfg.data["evaluator"]["step_limit"]))
    eval_ms = _timed_ms(lambda: evaluator.eval_term(term, [], defs))

    return {
        "modules": count,
        "symbol": symbol,
        "lookup_ms": lookup_ms,
        "resolve_ms": resolve_ms,
        "closure_indexed_ms": stats["elapsed_ms"],
        "closure_scan_ms": scan_stats["elapsed_ms"],
        "eval_ms": eval_ms,
        "closure_indexed_stats": stats["stats"],
        "closure_scan_stats": scan_stats["stats"],
    }


def _timed_ms(fn) -> float:
    start = time.perf_counter()
    fn()
    return (time.perf_counter() - start) * 1000.0


def _timed_result(fn) -> dict:
    start = time.perf_counter()
    defs, stats = fn()
    elapsed = (time.perf_counter() - start) * 1000.0
    return defs, {"elapsed_ms": elapsed, "stats": stats}


def _write_outputs(out_dir: Path, results: dict) -> None:
    results_path = out_dir / "results.json"
    summary_path = out_dir / "summary.md"
    results_path.write_text(json.dumps(results, sort_keys=True, indent=2), encoding="utf-8")
    lines = ["# Scaling Experiment Summary", ""]
    if results.get("measurements"):
        last = results["measurements"][-1]
        lines.append(f"- modules: {last.get('modules')}")
        lines.append(f"- lookup_ms: {last.get('lookup_ms')}")
        lines.append(f"- closure_indexed_ms: {last.get('closure_indexed_ms')}")
        lines.append(f"- closure_scan_ms: {last.get('closure_scan_ms')}")
        lines.append(f"- resolve_ms: {last.get('resolve_ms')}")
        lines.append(f"- eval_ms: {last.get('eval_ms')}")
    summary_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _meta_info(cfg: Config) -> dict:
    return {
        "git_commit": _git_commit(_repo_root()),
        "config_hash": _config_hash(cfg.data),
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


def _int_add_def(name: str, k: int) -> dict:
    return _definition(
        name,
        [{"name": "n", "type": {"tag": "int"}}],
        {"tag": "int"},
        _prim("add", _var("n"), _int_lit(k)),
    )


def _definition(name: str, params: list[dict], ret_type: dict, body: dict) -> dict:
    return {
        "name": name,
        "params": params,
        "ret_type": ret_type,
        "body": body,
        "termination": {"kind": "structural", "decreases_param": None},
    }


def _var(name: str) -> dict:
    return {"tag": "var", "name": name}


def _int_lit(value: int) -> dict:
    return {"tag": "int", "value": int(value)}


def _prim(op: str, *args: dict) -> dict:
    return {"tag": "prim", "op": op, "args": list(args)}


def _app_sym(name: str, args: list[dict]) -> dict:
    return {"tag": "app", "fn": {"tag": "sym", "name": name}, "args": args}
