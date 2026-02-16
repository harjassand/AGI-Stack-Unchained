#!/usr/bin/env python3
"""Equivalence harness for Omega verifier implementations."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _ensure_repo_import_path() -> None:
    roots = [str(_REPO_ROOT), str(_REPO_ROOT / "CDEL-v2")]
    for root in reversed(roots):
        if root not in sys.path:
            sys.path.insert(0, root)


def _load_verifier_module(module_name: str) -> Any:
    _ensure_repo_import_path()
    return importlib.import_module(module_name)


def _run_verifier(module_name: str, state_dir: Path) -> dict[str, Any]:
    cmd = [sys.executable, "-m", module_name, "--mode", "full", "--state_dir", str(state_dir)]
    start_ns = time.perf_counter_ns()
    run = subprocess.run(
        cmd,
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **{"PYTHONPATH": f"{_REPO_ROOT}:{_REPO_ROOT / 'CDEL-v2'}:{os.environ.get('PYTHONPATH', '')}".rstrip(":")}},
    )
    elapsed_ns = time.perf_counter_ns() - start_ns
    lines = [line.strip() for line in run.stdout.splitlines() if line.strip()]
    verdict = lines[-1] if lines else ""
    return {
        "return_code": int(run.returncode),
        "verdict": verdict,
        "elapsed_ns": int(elapsed_ns),
        "stdout_tail": "\n".join(lines[-20:]),
        "stderr_tail": "\n".join(run.stderr.splitlines()[-20:]),
    }


def _latest_payload(path: Path, suffix: str) -> dict[str, Any] | None:
    rows = sorted(path.glob(f"sha256_*.{suffix}"))
    if not rows:
        return None
    best: dict[str, Any] | None = None
    best_tick = -1
    for row in rows:
        payload = json.loads(row.read_text(encoding="utf-8"))
        tick_u64 = int(payload.get("tick_u64", -1))
        if tick_u64 >= best_tick:
            best_tick = tick_u64
            best = payload
    return best


def _module_fingerprints(module: Any, state_dir: Path) -> dict[str, str]:
    for required_attr in (
        "_resolve_state_dir",
        "_verify_hash_binding",
        "_recompute_observation_from_sources",
        "_decision_inputs_hash",
        "find_by_hash",
        "recompute_head",
        "canon_hash_obj",
    ):
        if not hasattr(module, required_attr):
            raise RuntimeError(f"candidate missing required verifier helper: {required_attr}")

    state_root, _daemon_root = module._resolve_state_dir(state_dir)  # type: ignore[attr-defined]
    state_payload = _latest_payload(state_root / "state", "omega_state_v1.json")
    if not isinstance(state_payload, dict):
        raise RuntimeError("missing omega_state_v1 payload")

    snapshot_hash = str(state_payload.get("snapshot_hash", ""))
    if snapshot_hash:
        snapshot_payload = module._verify_hash_binding(  # type: ignore[attr-defined]
            module.find_by_hash(state_root / "snapshot", "omega_tick_snapshot_v1.json", snapshot_hash),
            snapshot_hash,
            "omega_tick_snapshot_v1",
        )
    else:
        snapshot_payload = _latest_payload(state_root / "snapshot", "omega_tick_snapshot_v1.json")
        if not isinstance(snapshot_payload, dict):
            raise RuntimeError("missing snapshot payload")

    observation_hash = str(snapshot_payload.get("observation_report_hash", ""))
    decision_hash = str(snapshot_payload.get("decision_plan_hash", ""))
    trace_hash = str(snapshot_payload.get("trace_hash_chain_hash", ""))
    if not observation_hash or not decision_hash or not trace_hash:
        raise RuntimeError("snapshot missing required hash fields")

    observation_payload = module._verify_hash_binding(  # type: ignore[attr-defined]
        module.find_by_hash(state_root / "observations", "omega_observation_report_v1.json", observation_hash),
        observation_hash,
        "omega_observation_report_v1",
    )
    decision_payload = module._verify_hash_binding(  # type: ignore[attr-defined]
        module.find_by_hash(state_root / "decisions", "omega_decision_plan_v1.json", decision_hash),
        decision_hash,
        "omega_decision_plan_v1",
    )
    trace_payload = module._verify_hash_binding(  # type: ignore[attr-defined]
        module.find_by_hash(state_root / "ledger", "omega_trace_hash_chain_v1.json", trace_hash),
        trace_hash,
        "omega_trace_hash_chain_v1",
    )

    recomputed_obs = module._recompute_observation_from_sources(  # type: ignore[attr-defined]
        root=module._repo_root(),  # type: ignore[attr-defined]
        observation_payload=observation_payload,
        policy_hash=str(state_payload.get("policy_hash", "")),
        registry_hash=str(state_payload.get("registry_hash", "")),
        objectives_hash=str(state_payload.get("objectives_hash", "")),
    )
    recomputed_observation_hash = str(module.canon_hash_obj(recomputed_obs))  # type: ignore[attr-defined]
    decision_inputs_hash = str(module._decision_inputs_hash(decision_payload))  # type: ignore[attr-defined]
    artifact_hashes = trace_payload.get("artifact_hashes")
    if not isinstance(artifact_hashes, list):
        raise RuntimeError("trace payload missing artifact_hashes")
    recomputed_trace_head = str(
        module.recompute_head(  # type: ignore[attr-defined]
            str(trace_payload.get("H0", "")),
            [str(row) for row in artifact_hashes],
        )
    )

    return {
        "recomputed_observation_hash": recomputed_observation_hash,
        "decision_inputs_hash": decision_inputs_hash,
        "trace_head_hash": str(trace_payload.get("H_final", "")),
        "recomputed_trace_head_hash": recomputed_trace_head,
    }


def _corpus_state_dirs(corpus_root: Path) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    if not corpus_root.exists() or not corpus_root.is_dir():
        return out
    index_path = corpus_root / "INDEX.json"
    if index_path.exists() and index_path.is_file():
        try:
            index_payload = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            index_payload = {}
        rows = index_payload.get("cases")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                case_id = str(row.get("case_id", "")).strip()
                source_rel = str(row.get("source_state_dir_rel", "")).strip()
                candidate: Path | None = None
                if case_id:
                    state_link = corpus_root / case_id / "state"
                    if state_link.exists():
                        candidate = state_link.resolve()
                if candidate is None and source_rel:
                    source_path = (_REPO_ROOT / source_rel).resolve()
                    if source_path.exists():
                        candidate = source_path
                if candidate is None:
                    continue
                if not (candidate / "snapshot").is_dir() or not (candidate / "state").is_dir():
                    continue
                key = candidate.as_posix()
                if key in seen:
                    continue
                seen.add(key)
                out.append(candidate)
    for path in sorted(corpus_root.glob("**/state"), key=lambda row: row.as_posix()):
        candidate = path.resolve() if path.is_symlink() else path
        if (candidate / "snapshot").is_dir() and (candidate / "state").is_dir():
            key = candidate.as_posix()
            if key in seen:
                continue
            seen.add(key)
            out.append(candidate)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(prog="verifier_equivalence_suite_v1")
    parser.add_argument("--candidate_module", required=True)
    parser.add_argument("--reference_module", default="cdel.v18_0.verify_rsi_omega_daemon_v1")
    parser.add_argument("--corpus_root", default="tools/omega/verifier_corpus_v1")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    corpus_root = (_REPO_ROOT / str(args.corpus_root)).resolve() if not str(args.corpus_root).startswith("/") else Path(args.corpus_root).resolve()
    cases = _corpus_state_dirs(corpus_root)
    if not cases:
        raise SystemExit("no corpus state dirs found")

    reference_module = _load_verifier_module(str(args.reference_module))
    candidate_module = _load_verifier_module(str(args.candidate_module))

    mismatches: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    total_ref_ns = 0
    total_cand_ns = 0
    for state_dir in cases:
        reference = _run_verifier(str(args.reference_module), state_dir)
        candidate = _run_verifier(str(args.candidate_module), state_dir)
        total_ref_ns += int(reference["elapsed_ns"])
        total_cand_ns += int(candidate["elapsed_ns"])
        try:
            reference_fp = _module_fingerprints(reference_module, state_dir)
            candidate_fp = _module_fingerprints(candidate_module, state_dir)
            fp_error: str | None = None
        except Exception as exc:  # noqa: BLE001
            reference_fp = {}
            candidate_fp = {}
            fp_error = f"{type(exc).__name__}: {exc}"

        verdict_match = (
            int(reference["return_code"]) == int(candidate["return_code"])
            and str(reference["verdict"]) == str(candidate["verdict"])
        )
        fingerprint_match = fp_error is None and reference_fp == candidate_fp
        match = bool(verdict_match and fingerprint_match)
        row = {
            "state_dir": state_dir.as_posix(),
            "reference": reference,
            "candidate": candidate,
            "reference_fingerprints": reference_fp,
            "candidate_fingerprints": candidate_fp,
            "fingerprint_error": fp_error,
            "verdict_match_b": bool(verdict_match),
            "fingerprint_match_b": bool(fingerprint_match),
            "match_b": bool(match),
        }
        rows.append(row)
        if not match:
            mismatches.append(row)

    speedup = 0.0
    if total_cand_ns > 0:
        speedup = float(total_ref_ns) / float(total_cand_ns)
    payload = {
        "schema_version": "OMEGA_VERIFIER_EQUIVALENCE_REPORT_v1",
        "reference_module": str(args.reference_module),
        "candidate_module": str(args.candidate_module),
        "corpus_root": corpus_root.as_posix(),
        "cases_u64": int(len(rows)),
        "mismatches_u64": int(len(mismatches)),
        "equivalence_pass_b": int(len(mismatches)) == 0,
        "reference_total_ns_u64": int(total_ref_ns),
        "candidate_total_ns_u64": int(total_cand_ns),
        "candidate_speedup_vs_reference": float(speedup),
        "rows": rows,
    }

    if args.out:
        out_path = Path(args.out).resolve()
    else:
        out_path = _REPO_ROOT / "runs" / "OMEGA_VERIFIER_EQUIVALENCE_REPORT_v1.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    if payload["equivalence_pass_b"]:
        print("PASS")
    else:
        print("FAIL")
    print(out_path.as_posix())
    if not payload["equivalence_pass_b"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
