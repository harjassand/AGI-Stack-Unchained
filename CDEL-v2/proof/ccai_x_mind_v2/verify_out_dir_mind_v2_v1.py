#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

CDEL_ROOT = Path(__file__).resolve().parents[2]
if (CDEL_ROOT / "cdel").is_dir():
    sys.path.insert(0, str(CDEL_ROOT))

from cdel.canon.json_canon_v1 import loads, sha256_hex
from cdel.sealed.harnesses.ccai_x_mind_v1 import to_gcj1_bytes
from cdel.sealed.harnesses.ccai_x_mind_v1.errors_v1 import CCAI_MIND_C4_NOT_INTERVENTIONAL
from cdel.sealed.harnesses.ccai_x_mind_v1.harness_v1 import _compute_mind_v2_episode_score
from cdel.sealed.harnesses.ccai_x_mind_v1.suitepack_loader_v1 import load_suitepacks
from cdel.sealed.harnesses.ccai_x_mind_v2.candidate_loader_v2 import load_candidate_tar_v2
from cdel.sealed.harnesses.ccai_x_mind_v2.registry_diff_v1 import apply_registry_diff


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


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _hash_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _base_registry_path() -> Path:
    return CDEL_ROOT / "cdel" / "sealed" / "harnesses" / "ccai_x_mind_v2" / "fixtures" / "base_registry.json"


def _compute_scores_and_witnesses(candidate, suitepack_dir: Path) -> tuple[dict[str, int], dict[str, Any]]:
    suitepacks = load_suitepacks(suitepack_dir)
    scores: dict[str, list[int]] = {}
    confounding: list[dict[str, Any]] = []
    policy_swap: list[dict[str, Any]] = []
    identifiability: list[dict[str, Any]] = []
    invariance_v2: list[dict[str, Any]] = []

    for suitepack in suitepacks:
        for episode in suitepack.episodes:
            family = str(episode.data.get("suite_family", ""))
            score, witness = _compute_mind_v2_episode_score(family, episode.data, candidate)
            scores.setdefault(family, []).append(int(score))
            if witness:
                if family == "confounding_shift":
                    confounding.append(witness)
                elif family == "policy_swap_invariance":
                    policy_swap.append(witness)
                elif family == "edge_identifiability":
                    identifiability.append(witness)
                invariance_v2.append(witness)

    means = {family: (sum(vals) // len(vals) if vals else 0) for family, vals in scores.items()}
    score_total_fp = min(means.values()) if means else 0
    witness_payloads = {
        "confounding_witness.json": {
            "format": "confounding_witness_v1",
            "schema_version": "1",
            "episodes": confounding,
        },
        "policy_swap_witness.json": {
            "format": "policy_swap_witness_v1",
            "schema_version": "1",
            "episodes": policy_swap,
        },
        "identifiability_witness.json": {
            "format": "identifiability_witness_v1",
            "schema_version": "1",
            "episodes": identifiability,
        },
        "invariance_witness_v2.json": {
            "format": "invariance_witness_v2",
            "schema_version": "1",
            "episodes": invariance_v2,
        },
    }
    return means, {"score_total_fp": int(score_total_fp), "witness_payloads": witness_payloads}


def _verify_run(
    run_dir: Path,
    candidate,
    suitepack_dir: Path,
    expect_pass: bool,
    diff_hash: str,
    expected_fail_code: str | None = None,
) -> None:
    eval_result = _load_json(run_dir / "eval_result.json")
    status = str(eval_result.get("status", ""))
    if expect_pass:
        _assert(status == "PASS", f"expected PASS in {run_dir}, got {status}")
        receipt_path = run_dir / "receipt.json"
        _assert(receipt_path.exists() and receipt_path.stat().st_size > 0, "missing receipt on PASS")
    else:
        _assert(status == "FAIL", f"expected FAIL in {run_dir}, got {status}")
        if expected_fail_code is not None:
            fail_code = str(eval_result.get("fail_reason", {}).get("code", ""))
            _assert(fail_code == expected_fail_code, f"unexpected fail code: {fail_code}")
        receipt_path = run_dir / "receipt.json"
        _assert(not receipt_path.exists(), "receipt present on FAIL")

    evidence_dir = run_dir / "evidence"
    for name in [
        "blanket_attestation.json",
        "transcript.jsonl",
        "intervention_log.jsonl",
        "efe_report.jsonl",
        "efe_recompute.jsonl",
        "workspace_state.jsonl",
        "coherence_report.jsonl",
        "affordance_latent.jsonl",
    ]:
        _assert((evidence_dir / name).exists(), f"missing evidence {name}")

    if expect_pass:
        for name in [
            "confounding_witness.json",
            "policy_swap_witness.json",
            "identifiability_witness.json",
            "invariance_witness_v2.json",
        ]:
            _assert((evidence_dir / name).exists(), f"missing witness {name}")

    # EFE bindings include diff hash
    efe_rows = _load_jsonl(evidence_dir / "efe_report.jsonl")
    for row in efe_rows:
        bindings = row.get("artifact_hashes", {})
        _assert(bindings.get("mechanism_registry_diff_sha256") == diff_hash, "diff hash missing in EFE bindings")

    # Score provenance (PASS only)
    if expect_pass:
        suite_scores, info = _compute_scores_and_witnesses(candidate, suitepack_dir)
        summary = eval_result.get("summary", {})
        _assert(summary.get("suite_scores") == suite_scores, "suite scores mismatch")
        _assert(summary.get("score_total_fp") == info["score_total_fp"], "score_total_fp mismatch")

        # Witness recompute
        for filename, payload in info["witness_payloads"].items():
            expected_bytes = to_gcj1_bytes(payload)
            actual_bytes = (evidence_dir / filename).read_bytes()
            _assert(expected_bytes == actual_bytes, f"witness mismatch: {filename}")


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: verify_out_dir_mind_v2_v1.py <out_dir>", file=sys.stderr)
        raise SystemExit(2)
    out_dir = Path(sys.argv[1]).resolve()

    candidate_pass = out_dir / "candidate_pass_mind_v2.tar"
    candidate_base = out_dir / "candidate_base_mind_v2.tar"
    _assert(candidate_pass.exists(), "candidate_pass_mind_v2.tar missing")
    _assert(candidate_base.exists(), "candidate_base_mind_v2.tar missing")

    candidate = load_candidate_tar_v2(candidate_pass)
    candidate_base = load_candidate_tar_v2(candidate_base)
    diff_bytes = candidate.raw_bytes["mechanism_registry_diff.json"]
    diff_hash = sha256_hex(diff_bytes)
    diff_hash_base = sha256_hex(candidate_base.raw_bytes["mechanism_registry_diff.json"])

    base_registry = _load_json(_base_registry_path())
    applied = apply_registry_diff(
        base_registry,
        candidate.mechanism_registry_diff,
        protected_vars={"c"},
        allowed_kernels={"linear", "switch", "noisy_sensor", "table"},
        max_param_abs_fp=2000,
    )
    _assert(to_gcj1_bytes(applied) == to_gcj1_bytes(candidate.mechanism_registry), "diff apply mismatch")

    repo_root = CDEL_ROOT.parent
    dev_suitepacks = repo_root / "agi-system" / "system_runtime" / "tasks" / "ccai_x_mind_v1" / "suitepacks_mind_v2" / "dev"
    heldout_suitepacks = out_dir / "heldout_suitepacks"
    _assert(dev_suitepacks.exists(), "dev suitepacks missing")
    _assert(heldout_suitepacks.exists(), "heldout suitepacks missing")

    _verify_run(out_dir / "runs" / "run1" / "pass_dev", candidate, dev_suitepacks, True, diff_hash)
    _verify_run(out_dir / "runs" / "run1" / "pass_heldout", candidate, heldout_suitepacks, True, diff_hash)
    _verify_run(
        out_dir / "runs" / "run1" / "fail_wrong_structure",
        candidate_base,
        dev_suitepacks,
        False,
        diff_hash_base,
        expected_fail_code=CCAI_MIND_C4_NOT_INTERVENTIONAL,
    )

    non_regression = out_dir / "non_regression_receipts.json"
    _assert(non_regression.exists(), "non_regression_receipts.json missing")

    # Determinism manifest check if present
    run1_manifest = out_dir / "mind_v2_manifest_run1.json"
    run2_manifest = out_dir / "mind_v2_manifest_run2.json"
    if run1_manifest.exists() and run2_manifest.exists():
        _assert(run1_manifest.read_bytes() == run2_manifest.read_bytes(), "manifest bytes differ")

    print("PASS")


if __name__ == "__main__":
    main()
