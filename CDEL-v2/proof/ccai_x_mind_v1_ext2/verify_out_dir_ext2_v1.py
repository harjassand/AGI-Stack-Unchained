#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from cdel.canon.json_canon_v1 import loads, sha256_hex
from cdel.sealed.harnesses.ccai_x_mind_v1.harness_v1 import load_plan_config
from cdel.sealed.harnesses.ccai_x_mind_v1.suitepack_loader_v1 import load_suitepacks
from cdel.sealed.harnesses.ccai_x_mind_v1.candidate_loader_v1 import load_candidate_tar


EXPECTED_ABLATIONS = {
    "A": "CCAI_MIND_C1_DO_MISMATCH",
    "B": "CCAI_MIND_PLAN_CONFIG_INVALID",
    "C": "CCAI_MIND_PLAN_CONFIG_INVALID",
    "D": "CCAI_MIND_C3_ADMISSIBILITY_VIOLATION",
    "E": "CCAI_MIND_C0_ENV_NOT_ALLOWLISTED",
    "F": "CCAI_MIND_JSON_FLOAT_DETECTED",
}


def _load_json(path: Path) -> dict[str, Any]:
    data = loads(path.read_bytes())
    if not isinstance(data, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return data


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise SystemExit(f"jsonl must end with newline: {path}")
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line:
            raise SystemExit(f"empty jsonl line: {path}")
        obj = loads(line)
        if not isinstance(obj, dict):
            raise SystemExit(f"jsonl line must be object: {path}")
        rows.append(obj)
    return rows


def _hash_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _verify_receipt(run_dir: Path, expect_pass: bool) -> None:
    receipt = run_dir / "receipt.json"
    if expect_pass:
        _assert(receipt.exists() and receipt.stat().st_size > 0, f"receipt missing for PASS: {run_dir}")
    else:
        _assert(not receipt.exists(), f"receipt present for FAIL: {run_dir}")


def _verify_evidence_hashes(run_dir: Path, eval_result: dict[str, Any]) -> None:
    evidence = eval_result.get("evidence", {})
    mapping = {
        "transcript_sha256": "transcript.jsonl",
        "intervention_log_sha256": "intervention_log.jsonl",
        "efe_agent_sha256": "efe_report.jsonl",
        "efe_recompute_sha256": "efe_recompute.jsonl",
        "workspace_state_sha256": "workspace_state.jsonl",
        "coherence_report_sha256": "coherence_report.jsonl",
        "affordance_latent_sha256": "affordance_latent.jsonl",
        "blanket_attestation_sha256": "blanket_attestation.json",
    }
    evidence_dir = run_dir / "evidence"
    for key, fname in mapping.items():
        path = evidence_dir / fname
        _assert(path.exists(), f"missing evidence file: {path}")
        expected = str(evidence.get(key, ""))
        _assert(expected == _hash_file(path), f"evidence hash mismatch: {fname}")


def _recompute_scores(run_dir: Path, plan_id: str) -> tuple[dict[str, int], int]:
    plan = load_plan_config(plan_id)
    suite_dir = plan.suitepack_dir
    if suite_dir is not None and not suite_dir.is_absolute():
        repo_root = Path(__file__).resolve().parents[3]
        suite_dir = (repo_root / suite_dir).resolve()
    suitepacks = load_suitepacks(suite_dir) if suite_dir else []
    candidate = load_candidate_tar(Path(run_dir).parent.parent / "candidate_pass_ext2.tar")

    transcript = _load_jsonl(run_dir / "evidence" / "transcript.jsonl")
    efe_rows = _load_jsonl(run_dir / "evidence" / "efe_report.jsonl")
    coherence_rows = _load_jsonl(run_dir / "evidence" / "coherence_report.jsonl")

    idx = 0
    suite_scores: dict[str, list[int]] = {}

    for suitepack in suitepacks:
        suite_family = str(suitepack.manifest.get("suite_family", ""))
        for episode in suitepack.episodes:
            max_steps = min(int(episode.data.get("max_steps", 0)), plan.max_steps_per_episode)
            if max_steps <= 0:
                continue
            step_slice = transcript[idx : idx + max_steps]
            efe_slice = efe_rows[idx : idx + max_steps]
            coherence_slice = coherence_rows[idx : idx + max_steps]
            _assert(len(step_slice) == max_steps, "transcript length mismatch")
            _assert(len(efe_slice) == max_steps, "efe length mismatch")
            _assert(len(coherence_slice) == max_steps, "coherence length mismatch")

            if plan.require_efe_bindings and efe_slice:
                expected = _artifact_hashes(candidate, suitepack)
                reported = efe_slice[0].get("artifact_hashes")
                _assert(isinstance(reported, dict), "efe artifact_hashes missing")
                _assert(reported == expected, "efe artifact_hashes mismatch")

            score = _episode_score(suite_family, episode.data, candidate, step_slice, efe_slice, coherence_slice)
            suite_scores.setdefault(suite_family, []).append(score)
            idx += max_steps

    means = {fam: sum(vals) // len(vals) for fam, vals in suite_scores.items() if vals}
    score_total_fp = min(means.values()) if means else 0
    return means, int(score_total_fp)


def _artifact_hashes(candidate, suitepack) -> dict[str, str]:
    return {
        "markov_blanket_spec_sha256": sha256_hex(candidate.raw_bytes["markov_blanket_spec.json"]),
        "do_map_sha256": sha256_hex(candidate.raw_bytes["do_map.json"]),
        "causal_mechanism_registry_sha256": sha256_hex(candidate.raw_bytes["causal_mechanism_registry.json"]),
        "inference_kernel_isa_sha256": sha256_hex(candidate.raw_bytes["inference_kernel_isa.json"]),
        "inference_kernel_program_sha256": sha256_hex(candidate.raw_bytes["inference_kernel_program.json"]),
        "policy_prior_sha256": sha256_hex(candidate.raw_bytes["policy_prior.json"]),
        "preference_capsule_sha256": sha256_hex(candidate.raw_bytes["preference_capsule.json"]),
        "coherence_operator_sha256": sha256_hex(candidate.raw_bytes["coherence_operator.json"]),
        "suite_manifest_sha256": suitepack.manifest_sha256,
    }


def _mechanism_params(candidate) -> tuple[int, int]:
    mechanisms = candidate.mechanism_registry.get("mechanisms", [])
    if not mechanisms:
        return 0, 0
    params = dict(mechanisms[0].get("params", {}))
    return int(params.get("w_fp", 0)), int(params.get("b_fp", 0))


def _episode_score(
    suite_family: str,
    episode: dict[str, Any],
    candidate,
    transcript_rows: list[dict[str, Any]],
    efe_rows: list[dict[str, Any]],
    coherence_rows: list[dict[str, Any]],
) -> int:
    if suite_family == "agency_effect":
        spec = episode.get("agency_effect", {}) if isinstance(episode.get("agency_effect"), dict) else {}
        actions = list(spec.get("actions", ["probe", "exploit"]))
        action_to_x = dict(spec.get("action_to_x", {"probe": 0, "exploit": 1}))
        scale_int = int(spec.get("scale_int", 1000))
        w_fp, b_fp = _mechanism_params(candidate)
        values: dict[str, int] = {}
        for action in actions:
            x_val = int(action_to_x.get(action, 0))
            raw = b_fp + w_fp * x_val
            p = max(0, min(scale_int, raw))
            values[action] = int(p)
        if len(actions) >= 2:
            a0, a1 = actions[0], actions[1]
            return int(2 * abs(values.get(a0, 0) - values.get(a1, 0)))
        return 0
    if suite_family == "psi_swap":
        actions = [row.get("action_token") for row in transcript_rows]
        probe_seen = any(action == "probe" for action in actions)
        exploit_before_probe = bool(actions and actions[0] == "exploit")
        return 1000 if probe_seen and not exploit_before_probe else 0
    if suite_family == "ambiguity_trap":
        if not efe_rows:
            return 0
        first = efe_rows[0]
        chosen_id = first.get("chosen_policy_id")
        ambiguity_term = 0
        chosen_action = ""
        for policy in first.get("policies", []):
            if policy.get("policy_id") == chosen_id:
                ambiguity_term = int(policy.get("ambiguity_fp", 0))
                chosen_action = str(policy.get("actions", [""])[0])
                break
        required = str(episode.get("ambiguity_requirements", {}).get("required_action", "probe"))
        return ambiguity_term if chosen_action == required else 0
    if suite_family == "invariance":
        spec = episode.get("invariance_requirements", {}) if isinstance(episode.get("invariance_requirements"), dict) else {}
        target_w_fp = int(spec.get("target_w_fp", 0))
        score_margin_fp = int(spec.get("score_margin_fp", 1000))
        w_fp, _ = _mechanism_params(candidate)
        residual = abs(w_fp - target_w_fp)
        return max(0, score_margin_fp - residual)
    if suite_family == "coherence":
        bound = int(candidate.coherence_operator.get("residual_bound_fp", 0))
        max_residual = 0
        for row in coherence_rows:
            max_residual = max(max_residual, int(row.get("residual_fp", 0)))
        return max(0, bound - max_residual)
    if suite_family == "tamper_dark_room":
        actions = [row.get("action_token") for row in transcript_rows]
        tamper_used = any(action == "tamper" for action in actions)
        return 0 if tamper_used else 1000
    return 0


def _verify_ablation_matrix(out_dir: Path) -> None:
    matrix_path = out_dir / "ablation_matrix.json"
    data = _load_json(matrix_path)
    baseline = data.get("baseline", {})
    _assert(baseline.get("status") == "PASS", "ablation baseline must PASS")
    _assert(baseline.get("receipt_present") is True, "ablation baseline receipt missing")

    ablations = data.get("ablations", {})
    for key, expected in EXPECTED_ABLATIONS.items():
        entry = ablations.get(key, {})
        _assert(entry.get("status") == "FAIL", f"ablation {key} must FAIL")
        _assert(entry.get("fail_code") == expected, f"ablation {key} fail_code mismatch")
        _assert(entry.get("receipt_present") is False, f"ablation {key} receipt present")


def _verify_baseline(out_dir: Path, manifest: dict[str, Any]) -> None:
    baseline = manifest.get("baseline_receipts")
    if not isinstance(baseline, list) or not baseline:
        raise SystemExit("baseline_receipts missing from manifest")
    baseline_dir = out_dir / "baseline_mind_v1"
    for entry in baseline:
        path = entry.get("path")
        expected = entry.get("sha256")
        if not path or not expected:
            raise SystemExit("baseline_receipts entry invalid")
        receipt_path = baseline_dir / path
        _assert(receipt_path.exists(), f"baseline receipt missing: {receipt_path}")
        _assert(_hash_file(receipt_path) == expected, f"baseline receipt hash mismatch: {receipt_path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify-out-dir-ext2")
    parser.add_argument("out_dir")
    args = parser.parse_args()
    out_dir = Path(args.out_dir).resolve()
    repo_root = Path(__file__).resolve().parents[3]
    try:
        import os

        os.chdir(repo_root / "CDEL-v2")
    except Exception:
        pass

    manifest = _load_json(out_dir / "rsi_success_manifest.json")
    candidate_tar = out_dir / "candidate_pass_ext2.tar"
    _assert(candidate_tar.exists(), "candidate_pass_ext2.tar missing")
    _assert(_hash_file(candidate_tar) == manifest.get("candidate_tar_sha256"), "candidate tar sha mismatch")

    _verify_ablation_matrix(out_dir)
    _verify_baseline(out_dir, manifest)

    dev_score_total = None
    for run_name, plan_id in ("pass_dev", "ccai_x_mind_v1_ext2_dev"), ("pass_heldout", "ccai_x_mind_v1_ext2_heldout"):
        run_dir = out_dir / "runs" / run_name
        eval_result = _load_json(run_dir / "eval_result.json")
        _assert(eval_result.get("status") == "PASS", f"{run_name} must PASS")
        _assert(eval_result.get("plan_id") == plan_id, f"{run_name} plan_id mismatch")
        _verify_receipt(run_dir, True)
        _verify_evidence_hashes(run_dir, eval_result)

        suite_scores, score_total_fp = _recompute_scores(run_dir, plan_id)
        summary = eval_result.get("summary", {})
        for family, mean in suite_scores.items():
            _assert(int(summary.get("suite_scores", {}).get(family, -1)) == mean, f"suite score mismatch for {family}")
        _assert(int(eval_result.get("score_total_fp", -1)) == score_total_fp, f"score_total_fp mismatch for {run_name}")
        if run_name == "pass_dev":
            dev_score_total = score_total_fp

    rsi_dir = out_dir / "rsi"
    metrics = _load_json(rsi_dir / "rsi_metrics.json")
    _assert(metrics.get("best_score_fp") == manifest.get("rsi_metrics", {}).get("best_score_fp"), "best_score_fp mismatch")
    if dev_score_total is not None:
        _assert(int(metrics.get("best_score_fp", -1)) == int(dev_score_total), "rsi best_score_fp mismatch")
        learning_state = _load_json(rsi_dir / "learning_state.json")
        _assert(int(learning_state.get("best_score_fp", -1)) == int(dev_score_total), "learning_state best_score_fp mismatch")

    print("PASS")


if __name__ == "__main__":
    main()
