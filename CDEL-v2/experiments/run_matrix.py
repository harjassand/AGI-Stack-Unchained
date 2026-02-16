"""Run an experiment matrix and write per-run artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from cdel.bench.experiment import (
    _build_config_json,
    _build_data,
    _hash_file,
    _hash_json,
    run_experiment,
)
from cdel.config import load_config


def _load_matrix(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("runs"), list):
        return data["runs"]
    raise ValueError("matrix must be a list or an object with 'runs'")


def _map_generator(mode: str) -> str:
    if mode in {"enum_reuse", "enum-reuse"}:
        return "enum-reuse"
    return mode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--only-run", default=None, help="comma-separated run_id list")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    run_args = sys.argv
    only_runs = None
    if args.only_run:
        only_runs = {name.strip() for name in args.only_run.split(",") if name.strip()}

    root = Path(args.root).resolve()
    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    matrix_path = Path(args.matrix).resolve()
    runs = _load_matrix(matrix_path)

    base_cfg = load_config(root)

    summary = {"runs": []}
    for run in runs:
        run_id = run.get("run_id")
        if not run_id:
            raise ValueError("run_id is required")
        if only_runs is not None and run_id not in only_runs:
            continue
        out_dir = out_root / run_id
        if out_dir.exists() and any(out_dir.iterdir()):
            if args.skip_existing:
                summary["runs"].append({"run_id": run_id, "status": "skipped_existing"})
                continue
            if not args.overwrite and not args.resume:
                legacy = not (out_dir / "STATUS.json").exists()
                summary["runs"].append(
                    {"run_id": run_id, "status": "legacy" if legacy else "incomplete"}
                )
                continue
            if args.overwrite:
                shutil.rmtree(out_dir)

        tasks_path = root / run.get("tasks_file")
        generator = _map_generator(run.get("generator_mode", "enum"))
        data = _build_data(
            base_cfg,
            run.get("budget"),
            run.get("cost_weights"),
            run.get("spec_domain"),
            run.get("eval_step_limit"),
        )
        config_json = _build_config_json(
            data,
            generator,
            run.get("seed"),
            tasks_path.resolve(),
            run.get("closure_cache"),
            run.get("certificate_mode"),
            run.get("load_mode"),
            run.get("proof_synth"),
        )
        config_hash = _hash_json(config_json)
        tasks_hash = _hash_file(tasks_path.resolve())

        done_path = out_dir / "DONE"
        status_path = out_dir / "STATUS.json"
        if done_path.exists():
            if status_path.exists():
                status = json.loads(status_path.read_text(encoding="utf-8"))
                if status.get("config_hash") != config_hash or status.get("tasks_hash") != tasks_hash:
                    raise ValueError(f"run config mismatch for completed run: {run_id}")
            summary["runs"].append({"run_id": run_id, "status": "complete"})
            continue

        if out_dir.exists() and any(out_dir.iterdir()) and args.resume:
            if not status_path.exists():
                summary["runs"].append({"run_id": run_id, "status": "legacy"})
                continue
            resume = True
        else:
            resume = False

        try:
            run_experiment(
                base_cfg,
                tasks_path,
                generator=generator,
                out_dir=out_dir,
                seed=run.get("seed"),
                budget_override=run.get("budget"),
                cost_weights=run.get("cost_weights"),
                spec_domain=run.get("spec_domain"),
                eval_step_limit=run.get("eval_step_limit"),
                closure_cache=run.get("closure_cache"),
                certificate_mode=run.get("certificate_mode"),
                load_mode=run.get("load_mode"),
                proof_synth=run.get("proof_synth"),
                resume=resume,
                run_args=run_args,
            )
            summary["runs"].append(
                {"run_id": run_id, "status": "complete", "resumed": bool(resume)}
            )
        except Exception as exc:  # pragma: no cover - best-effort summary
            summary["runs"].append(
                {"run_id": run_id, "status": "failed", "error": str(exc)}
            )

    summary_path = out_root / "matrix_run_summary.json"
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
