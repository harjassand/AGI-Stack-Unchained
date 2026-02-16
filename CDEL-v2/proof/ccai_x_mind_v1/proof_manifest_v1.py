#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

from cdel.canon.json_canon_v1 import canon_bytes, loads, sha256_hex


ZERO_HASH = "0" * 64


def _hash_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _load_json(path: Path) -> dict[str, Any]:
    data = loads(path.read_bytes())
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError(f"jsonl must end with newline: {path}")
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line:
            raise ValueError(f"empty jsonl line: {path}")
        row = loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"jsonl line is not object: {path}")
        rows.append(row)
    return rows


def _git_sha(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "UNKNOWN"


def _candidate_id_from_tar(path: Path) -> str:
    with tarfile.open(path, "r:*") as tf:
        manifest = tf.extractfile("manifest.json").read()
    obj = loads(manifest)
    if not isinstance(obj, dict):
        raise ValueError("manifest.json must be object")
    return str(obj.get("candidate_id", ""))


def _suitepack_receipts(suitepack_dir: Path) -> list[dict[str, str]]:
    receipts: list[dict[str, str]] = []
    if (suitepack_dir / "suite_manifest.json").is_file():
        manifests = [suitepack_dir / "suite_manifest.json"]
    else:
        manifests = sorted(
            (p / "suite_manifest.json" for p in suitepack_dir.iterdir() if p.is_dir()),
            key=lambda p: p.parent.name,
        )
    for manifest_path in manifests:
        if not manifest_path.exists():
            continue
        manifest = _load_json(manifest_path)
        suitepack_id = str(manifest.get("suitepack_id", ""))
        receipts.append(
            {
                "suitepack_id": suitepack_id,
                "suite_manifest_sha256": _hash_file(manifest_path),
            }
        )
    receipts.sort(key=lambda item: item.get("suitepack_id", ""))
    return receipts


def _collect_run_info(run_dir: Path) -> dict[str, Any]:
    eval_result_path = run_dir / "eval_result.json"
    eval_result = _load_json(eval_result_path)
    status = str(eval_result.get("status", ""))
    fail_code = str(eval_result.get("fail_reason", {}).get("code", ""))

    evidence_dir = run_dir / "evidence"
    evidence_files = [
        "blanket_attestation.json",
        "transcript.jsonl",
        "intervention_log.jsonl",
        "efe_report.jsonl",
        "efe_recompute.jsonl",
        "workspace_state.jsonl",
        "coherence_report.jsonl",
        "affordance_latent.jsonl",
    ]
    evidence_hashes: list[dict[str, str]] = []
    for name in sorted(evidence_files):
        path = evidence_dir / name
        evidence_hashes.append({"path": str(path.relative_to(run_dir)), "sha256": _hash_file(path)})

    intervention_rows = _load_jsonl(evidence_dir / "intervention_log.jsonl")
    workspace_rows = _load_jsonl(evidence_dir / "workspace_state.jsonl")
    coherence_rows = _load_jsonl(evidence_dir / "coherence_report.jsonl")

    final_link_hash = intervention_rows[-1].get("link_hash", ZERO_HASH) if intervention_rows else ZERO_HASH
    final_state_hash = workspace_rows[-1].get("state_hash", ZERO_HASH) if workspace_rows else ZERO_HASH
    max_residual = 0
    for row in coherence_rows:
        try:
            residual = int(row.get("residual_fp", 0))
        except Exception:
            residual = 0
        if residual > max_residual:
            max_residual = residual

    receipt_path = run_dir / "receipt.json"
    receipt_sha256 = _hash_file(receipt_path) if receipt_path.exists() else ""

    return {
        "run_label": run_dir.name,
        "status": status,
        "fail_code": fail_code,
        "eval_result_sha256": _hash_file(eval_result_path),
        "receipt_sha256": receipt_sha256,
        "evidence_sha256": evidence_hashes,
        "final_intervention_log_link_hash": final_link_hash,
        "final_workspace_state_hash": final_state_hash,
        "max_coherence_residual_fp": int(max_residual),
    }


def _collect_fail_fixtures(run_root: Path, expected: dict[str, str]) -> dict[str, Any]:
    fixtures: dict[str, Any] = {}
    for name, code in expected.items():
        run_dir = run_root / name
        info = _collect_run_info(run_dir)
        info["expected_fail_code"] = code
        fixtures[name] = info
    return fixtures


def _collect_rsi_info(rsi_dir: Path, out_root: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"run_dir": str(rsi_dir.relative_to(out_root))}
    state_path = rsi_dir / "learning_state.json"
    if state_path.exists():
        info["learning_state_sha256"] = _hash_file(state_path)
        info["learning_state"] = _load_json(state_path)

    epochs: list[dict[str, Any]] = []
    for epoch_dir in sorted(rsi_dir.glob("epoch_*")):
        eval_path = epoch_dir / "sealed_eval" / "eval_result.json"
        if not eval_path.exists():
            continue
        eval_obj = _load_json(eval_path)
        epochs.append(
            {
                "epoch": epoch_dir.name,
                "status": str(eval_obj.get("status", "")),
                "suite_scores": eval_obj.get("summary", {}).get("suite_scores", {}),
            }
        )
    info["epochs"] = epochs
    return info


def _build_core_manifest(
    *,
    out_root: Path,
    candidate_tar: Path,
    dev_suitepacks: Path,
    heldout_suitepacks: Path,
    run_dev_dir: Path,
    run_heldout_dir: Path,
    fail_run_root: Path,
    expected_failures: dict[str, str],
    rsi_dir: Path,
    seed: int,
) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    cdel_root = Path(__file__).resolve().parents[2]
    return {
        "format": "ccai_x_mind_proof_manifest_v1",
        "schema_version": "1",
        "tool_versions": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "genesis_git_sha": _git_sha(repo_root / "Genesis"),
            "agi_system_git_sha": _git_sha(repo_root / "agi-system"),
            "cdel_git_sha": _git_sha(cdel_root),
        },
        "inputs": {
            "seed": int(seed),
            "candidate_id": _candidate_id_from_tar(candidate_tar),
            "candidate_tar_sha256": _hash_file(candidate_tar),
            "plan_ids": {
                "dev": "ccai_x_mind_v1_sealed_dev",
                "heldout": "ccai_x_mind_v1_sealed_heldout",
            },
        },
        "suitepacks": {
            "dev": _suitepack_receipts(dev_suitepacks),
            "heldout": _suitepack_receipts(heldout_suitepacks),
        },
        "runs": {
            "pass_dev": _collect_run_info(run_dev_dir),
            "pass_heldout": _collect_run_info(run_heldout_dir),
        },
        "fail_fixtures": _collect_fail_fixtures(fail_run_root, expected_failures),
        "rsi_loop": _collect_rsi_info(rsi_dir, out_root),
        "determinism": {
            "run1_manifest_sha256": ZERO_HASH,
            "run2_manifest_sha256": ZERO_HASH,
            "determinism_ok": False,
        },
    }


def _write_manifest(path: Path, payload: dict[str, Any]) -> str:
    data = canon_bytes(payload)
    path.write_bytes(data)
    return sha256_hex(data)


def main() -> int:
    parser = argparse.ArgumentParser(prog="ccai-x-mind-proof-manifest")
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--candidate_tar", required=True)
    parser.add_argument("--dev_suitepacks", required=True)
    parser.add_argument("--heldout_suitepacks", required=True)
    parser.add_argument("--rsi_dir", required=True)
    parser.add_argument("--expected_failures", required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()

    out_root = Path(args.out_dir).resolve()
    candidate_tar = Path(args.candidate_tar).resolve()
    dev_suitepacks = Path(args.dev_suitepacks).resolve()
    heldout_suitepacks = Path(args.heldout_suitepacks).resolve()
    rsi_dir = Path(args.rsi_dir).resolve()
    expected_failures = json.loads(Path(args.expected_failures).read_text(encoding="utf-8"))

    run1_root = out_root / "runs" / "run1"
    run2_root = out_root / "runs" / "run2"

    core1 = _build_core_manifest(
        out_root=out_root,
        candidate_tar=candidate_tar,
        dev_suitepacks=dev_suitepacks,
        heldout_suitepacks=heldout_suitepacks,
        run_dev_dir=run1_root / "pass_dev",
        run_heldout_dir=run1_root / "pass_heldout",
        fail_run_root=run1_root,
        expected_failures=expected_failures,
        rsi_dir=rsi_dir,
        seed=int(args.seed),
    )

    core2 = _build_core_manifest(
        out_root=out_root,
        candidate_tar=candidate_tar,
        dev_suitepacks=dev_suitepacks,
        heldout_suitepacks=heldout_suitepacks,
        run_dev_dir=run2_root / "pass_dev",
        run_heldout_dir=run2_root / "pass_heldout",
        fail_run_root=run1_root,
        expected_failures=expected_failures,
        rsi_dir=rsi_dir,
        seed=int(args.seed),
    )

    core1_sha = sha256_hex(canon_bytes(core1))
    core2_sha = sha256_hex(canon_bytes(core2))
    determinism_ok = core1_sha == core2_sha

    for core in (core1, core2):
        core["determinism"]["run1_manifest_sha256"] = core1_sha
        core["determinism"]["run2_manifest_sha256"] = core2_sha
        core["determinism"]["determinism_ok"] = determinism_ok

    _write_manifest(out_root / "proof_manifest_run1.json", core1)
    _write_manifest(out_root / "proof_manifest_run2.json", core2)

    if not determinism_ok:
        raise SystemExit("determinism check failed: run manifests differ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
