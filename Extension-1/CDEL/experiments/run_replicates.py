"""Run matrix experiments across multiple seeds."""

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


def _parse_seeds(value: str) -> list[int]:
    seeds = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        seeds.append(int(part))
    if not seeds:
        raise ValueError("no seeds specified")
    return seeds


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--seeds", required=True, help="comma-separated seed list, e.g. 0,1,2")
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--overwrite-legacy", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    run_args = sys.argv

    root = Path(args.root).resolve()
    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    matrix_path = Path(args.matrix).resolve()
    runs = _load_matrix(matrix_path)
    seeds = _parse_seeds(args.seeds)

    base_cfg = load_config(root)
    summary = {"runs": []}

    for run in runs:
        base_id = run.get("run_id")
        if not base_id:
            raise ValueError("run_id is required")
        for seed in seeds:
            run_id = f"{base_id}_s{seed}"
            out_dir = out_root / run_id
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
                seed,
                tasks_path.resolve(),
                run.get("closure_cache"),
                run.get("certificate_mode"),
                run.get("load_mode"),
                run.get("proof_synth"),
            )
            config_hash = _hash_json(config_json)
            tasks_hash = _hash_file(tasks_path.resolve())

            status_path = out_dir / "STATUS.json"
            done_path = out_dir / "DONE"
            failed_path = out_dir / "FAILED.json"
            legacy = out_dir.exists() and any(out_dir.iterdir()) and not status_path.exists()

            if done_path.exists():
                if not status_path.exists():
                    if args.overwrite_legacy or args.overwrite:
                        shutil.rmtree(out_dir)
                        legacy = False
                    else:
                        summary["runs"].append({"run_id": run_id, "status": "legacy"})
                        continue
                else:
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                    if status.get("config_hash") != config_hash or status.get("tasks_hash") != tasks_hash:
                        raise ValueError(f"run config mismatch for completed run: {run_id}")
                    summary["runs"].append({"run_id": run_id, "status": "complete"})
                    continue

            if failed_path.exists() and not args.retry_failed:
                summary["runs"].append({"run_id": run_id, "status": "failed"})
                continue
            if failed_path.exists() and args.retry_failed:
                failed_path.unlink()

            if legacy:
                if args.overwrite_legacy or args.overwrite:
                    shutil.rmtree(out_dir)
                else:
                    summary["runs"].append({"run_id": run_id, "status": "legacy"})
                    continue

            resume = False
            if out_dir.exists() and any(out_dir.iterdir()):
                if args.skip_existing and not args.resume:
                    summary["runs"].append({"run_id": run_id, "status": "skipped_existing"})
                    continue
                if args.overwrite and not args.resume:
                    shutil.rmtree(out_dir)
                elif args.resume:
                    if not status_path.exists():
                        summary["runs"].append({"run_id": run_id, "status": "legacy"})
                        continue
                    resume = True
                else:
                    summary["runs"].append({"run_id": run_id, "status": "incomplete"})
                    continue

            try:
                run_experiment(
                    base_cfg,
                    tasks_path,
                    generator=generator,
                    out_dir=out_dir,
                    seed=seed,
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
                summary["runs"].append({"run_id": run_id, "status": "failed", "error": str(exc)})

    summary_path = out_root / "replicates_run_summary.json"
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
