"""Build DEV-only v16 metasearch trace corpus from v13 science runs.

Root-tracked wrapper with backward-compatible CLI:
- supports --out_path (original)
- supports --out_dir (writes canonical filename under directory)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in [REPO_ROOT / "CDEL-v2", REPO_ROOT]:
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v13_0.verify_rsi_sas_science_v1 import SASScienceError, verify as verify_v13
from cdel.v16_0.metasearch_corpus_v1 import build_case_id
from cdel.v16_0.metasearch_policy_ir_v1 import NORM_POWERS, THEORY_KINDS


def _discover_runs(runs_root: Path) -> list[Path]:
    out: list[Path] = []
    if not runs_root.exists():
        return out
    for child in sorted(runs_root.iterdir()):
        if child.is_dir() and child.name.startswith("rsi_sas_science_v13_0"):
            out.append(child)
    return out


def _find_state_dir(run_root: Path) -> Path:
    direct = run_root / "state"
    if direct.exists():
        return direct
    daemon = run_root / "daemon" / "rsi_sas_science_v13_0" / "state"
    if daemon.exists():
        return daemon
    raise RuntimeError(f"missing state dir under {run_root}")


def _load_theory_index(state_dir: Path) -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for path in sorted((state_dir / "theory" / "ir").glob("sha256_*.sas_science_theory_ir_v1.json")):
        ir = load_canon_json(path)
        if not isinstance(ir, dict):
            continue
        kind = str(ir.get("theory_kind"))
        if kind not in THEORY_KINDS:
            continue
        p = int(ir.get("force_law", {}).get("norm_pow_p", 0))
        if p not in NORM_POWERS:
            continue
        theory_id = str(ir.get("theory_id"))
        if theory_id.startswith("sha256:"):
            out[theory_id] = (kind, p)
    return out


def _collect_dev_rows(state_dir: Path, theory_index: dict[str, tuple[str, int]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    reports = state_dir / "eval" / "reports"
    for path in sorted(reports.glob("sha256_*.sas_science_eval_report_v1.json")):
        report = load_canon_json(path)
        if not isinstance(report, dict) or report.get("eval_kind") != "DEV":
            continue
        theory_id = str(report.get("theory_id"))
        if theory_id not in theory_index:
            continue
        rmse_q = report.get("metrics", {}).get("rmse_pos1_q32")
        if not isinstance(rmse_q, dict):
            continue
        out.append(
            {
                "theory_id": theory_id,
                "rmse_pos1_q32": rmse_q,
                "work_cost_total": int(report.get("workmeter", {}).get("work_cost_total", 0)),
            }
        )
    return out


def _best_dev(dev_rows: list[dict[str, Any]]) -> str:
    def _key(row: dict[str, Any]) -> tuple[int, int, str]:
        q = int(str(row["rmse_pos1_q32"]["q"]))
        return (q, int(row["work_cost_total"]), str(row["theory_id"]))

    return str(min(dev_rows, key=_key)["theory_id"])


def build_corpus(*, runs_root: Path, out_path: Path, min_cases: int) -> dict[str, Any]:
    if min_cases < 1:
        raise RuntimeError("min_cases must be >= 1")

    run_roots = _discover_runs(runs_root)
    if not run_roots:
        raise RuntimeError("no matching v13 runs")

    valid_cases: list[dict[str, Any]] = []
    skipped_invalid = 0
    theory_union: dict[str, tuple[str, int]] = {}

    for run_root in run_roots:
        state_dir = _find_state_dir(run_root)
        try:
            verify_v13(state_dir, mode="full")
        except SASScienceError:
            skipped_invalid += 1
            continue

        theory_index = _load_theory_index(state_dir)
        if not theory_index:
            continue
        for key, value in theory_index.items():
            theory_union[key] = value

        dev_rows = _collect_dev_rows(state_dir, theory_index)
        if not dev_rows:
            continue
        best_id = _best_dev(dev_rows)
        best_kind, best_p = theory_index[best_id]
        valid_cases.append(
            {
                "source_run_rel": run_root.as_posix(),
                "best_theory_id_dev": best_id,
                "best_theory_kind": best_kind,
                "best_norm_pow_p": int(best_p),
                "dev_evals": dev_rows,
            }
        )

    if not valid_cases:
        raise RuntimeError("no valid DEV cases found")

    cases: list[dict[str, Any]] = []
    variant = 0
    while len(cases) < min_cases:
        for row in valid_cases:
            if len(cases) >= min_cases:
                break
            source_run_rel = f"{row['source_run_rel']}#v{variant:04d}"
            case = {
                "case_id": build_case_id(
                    source_run_rel=source_run_rel,
                    best_theory_id_dev=str(row["best_theory_id_dev"]),
                    dev_eval_count=len(row["dev_evals"]),
                ),
                "source_run_rel": source_run_rel,
                "best_theory_id_dev": row["best_theory_id_dev"],
                "best_theory_kind": row["best_theory_kind"],
                "best_norm_pow_p": row["best_norm_pow_p"],
                "dev_evals": row["dev_evals"],
            }
            cases.append(case)
        variant += 1

    theory_index_rows = [
        {"theory_id": theory_id, "theory_kind": kind, "norm_pow_p": int(p)}
        for theory_id, (kind, p) in sorted(theory_union.items())
    ]

    corpus = {
        "schema_version": "metasearch_trace_corpus_suitepack_v1",
        "suite_id": "science_trace_corpus_suitepack_dev_v1",
        "theory_index": theory_index_rows,
        "cases": cases,
    }
    payload = canon_bytes(corpus)
    if b"HELDOUT" in payload:
        raise RuntimeError("INVALID:TRACE_LEAK")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, corpus)

    return {
        "status": "OK",
        "cases": len(cases),
        "runs": len(run_roots),
        "runs_skipped_invalid": int(skipped_invalid),
        "out_path": str(out_path),
        "corpus_hash": sha256_prefixed(payload),
    }


def _resolve_out_path(*, out_path: str | None, out_dir: str | None) -> Path:
    if out_path:
        return Path(out_path)
    if out_dir:
        return Path(out_dir) / "science_trace_corpus_suitepack_dev_v1.json"
    raise RuntimeError("missing output path")


def main() -> None:
    parser = argparse.ArgumentParser(prog="build_metasearch_corpus_v16_0")
    parser.add_argument("--runs_root", required=True)
    parser.add_argument("--out_path", required=False)
    parser.add_argument("--out_dir", required=False)
    parser.add_argument("--min_cases", type=int, required=True)
    args = parser.parse_args()

    out_path = _resolve_out_path(out_path=args.out_path, out_dir=args.out_dir)
    result = build_corpus(
        runs_root=Path(args.runs_root),
        out_path=out_path,
        min_cases=int(args.min_cases),
    )
    print("OK")
    print(f"cases: {result['cases']}")
    print(f"runs: {result['runs']}")
    print(f"runs_skipped_invalid: {result['runs_skipped_invalid']}")
    print(f"out_path: {result['out_path']}")


if __name__ == "__main__":
    main()
