"""Run a single experiment config with optional determinism check."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from cdel.bench.experiment import run_experiment
from cdel.config import load_config


def _map_generator(mode: str) -> str:
    if mode in {"enum_reuse", "enum-reuse"}:
        return "enum-reuse"
    return mode


def _load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_once(root: Path, cfg: dict, out_dir: Path) -> dict:
    base_cfg = load_config(root)
    return run_experiment(
        base_cfg,
        root / cfg["tasks_file"],
        generator=_map_generator(cfg.get("generator_mode", "enum")),
        out_dir=out_dir,
        seed=cfg.get("seed"),
        budget_override=cfg.get("budget"),
        cost_weights=cfg.get("cost_weights"),
        spec_domain=cfg.get("spec_domain"),
        eval_step_limit=cfg.get("eval_step_limit"),
        closure_cache=cfg.get("closure_cache"),
        certificate_mode=cfg.get("certificate_mode"),
        load_mode=cfg.get("load_mode"),
        proof_synth=cfg.get("proof_synth"),
        run_args=sys.argv,
    )


def _order_log(path: Path) -> str:
    return (path / "ledger" / "order.log").read_text(encoding="utf-8")


def _report_json(path: Path) -> str:
    return (path / "report.json").read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--determinism-check", action="store_true")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    cfg = _load_config(Path(args.config))

    if not args.determinism_check:
        out_dir = Path(args.out or "runs/single").resolve()
        if out_dir.exists():
            shutil.rmtree(out_dir)
        _run_once(root, cfg, out_dir)
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        out_a = tmp_path / "run_a"
        out_b = tmp_path / "run_b"
        _run_once(root, cfg, out_a)
        _run_once(root, cfg, out_b)

        if _order_log(out_a) != _order_log(out_b):
            raise SystemExit("order.log mismatch between determinism runs")
        if _report_json(out_a) != _report_json(out_b):
            raise SystemExit("report.json mismatch between determinism runs")


if __name__ == "__main__":
    main()
