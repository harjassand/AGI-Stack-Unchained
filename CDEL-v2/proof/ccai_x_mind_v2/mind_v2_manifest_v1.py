#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

CDEL_ROOT = Path(__file__).resolve().parents[2]
if (CDEL_ROOT / "cdel").is_dir():
    sys.path.insert(0, str(CDEL_ROOT))

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
    import tarfile

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
    score_total_fp = eval_result.get("summary", {}).get("score_total_fp")

    evidence_dir = run_dir / "evidence"
    evidence_hashes: list[dict[str, str]] = []
    for path in sorted(evidence_dir.rglob("*")):
        if path.is_file():
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
        "score_total_fp": score_total_fp,
        "eval_result_sha256": _hash_file(eval_result_path),
        "receipt_sha256": receipt_sha256,
        "evidence_sha256": evidence_hashes,
        "final_intervention_log_link_hash": final_link_hash,
        "final_workspace_state_hash": final_state_hash,
        "max_coherence_residual_fp": int(max_residual),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="mind-v2-manifest")
    parser.add_argument("--out_root", required=True)
    parser.add_argument("--candidate_pass_tar", required=True)
    parser.add_argument("--candidate_base_tar", required=True)
    parser.add_argument("--dev_suitepacks", required=True)
    parser.add_argument("--heldout_suitepacks", required=True)
    parser.add_argument("--pass_dev_dir", required=True)
    parser.add_argument("--pass_heldout_dir", required=True)
    parser.add_argument("--fail_dir", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out_path", required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    cdel_root = Path(__file__).resolve().parents[2]

    manifest = {
        "format": "ccai_x_mind_v2_proof_manifest_v1",
        "schema_version": "1",
        "tool_versions": {
            "python": f"{__import__('sys').version_info.major}.{__import__('sys').version_info.minor}.{__import__('sys').version_info.micro}",
            "genesis_git_sha": _git_sha(repo_root / "Genesis"),
            "agi_system_git_sha": _git_sha(repo_root / "agi-system"),
            "cdel_git_sha": _git_sha(cdel_root),
        },
        "inputs": {
            "seed": int(args.seed),
            "candidate_pass_id": _candidate_id_from_tar(Path(args.candidate_pass_tar)),
            "candidate_pass_tar_sha256": _hash_file(Path(args.candidate_pass_tar)),
            "candidate_base_id": _candidate_id_from_tar(Path(args.candidate_base_tar)),
            "candidate_base_tar_sha256": _hash_file(Path(args.candidate_base_tar)),
            "plan_ids": {
                "dev": "ccai_x_mind_v2_sealed_dev",
                "heldout": "ccai_x_mind_v2_sealed_heldout",
            },
            "suitepacks": {
                "dev": _suitepack_receipts(Path(args.dev_suitepacks)),
                "heldout": _suitepack_receipts(Path(args.heldout_suitepacks)),
            },
        },
        "runs": {
            "pass_dev": _collect_run_info(Path(args.pass_dev_dir)),
            "pass_heldout": _collect_run_info(Path(args.pass_heldout_dir)),
        },
        "fail_fixtures": {"wrong_structure": _collect_run_info(Path(args.fail_dir))},
    }

    out_path = Path(args.out_path)
    out_path.write_bytes(canon_bytes(manifest))


if __name__ == "__main__":
    main()
