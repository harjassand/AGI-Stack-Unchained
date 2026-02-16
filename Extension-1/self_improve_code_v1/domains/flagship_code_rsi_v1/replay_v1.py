"""Replay and verify utilities (v1.1)."""

from __future__ import annotations

import json
import os
import tarfile
from typing import Dict, List, Tuple

from ...canon.hash_v1 import sha256_hex
from ...canon.json_canon_v1 import canon_bytes
from ...package.tar_deterministic_v1 import write_deterministic_tar
from .candidate_v1 import compute_candidate_hashes
from .selection_v1 import select_topk_for_submission


def _read_json(path: str) -> Dict:
    with open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def _is_canonical(path: str) -> bool:
    raw = open(path, "rb").read()
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        return False
    return raw == canon_bytes(obj)


def _extract_tar(tar_path: str) -> Tuple[Dict, bytes]:
    with tarfile.open(tar_path, "r:*") as tf:
        manifest_data = tf.extractfile("manifest.json").read()
        patch_data = tf.extractfile("patch.diff").read()
    manifest = json.loads(manifest_data.decode("utf-8"))
    return manifest, patch_data


def _verify_candidate_tar(cand_dir: str, errors: List[str]) -> None:
    tar_path = os.path.join(cand_dir, "candidate.tar")
    manifest_path = os.path.join(cand_dir, "manifest.json")
    patch_path = os.path.join(cand_dir, "patch.diff")
    if not os.path.exists(tar_path):
        return
    try:
        manifest = _read_json(manifest_path)
        patch_bytes = open(patch_path, "rb").read()
    except Exception:
        errors.append(f"candidate bundle missing files in {cand_dir}")
        return
    _manifest_hash, _patch_hash, _policy_hash, bundle_hash = compute_candidate_hashes(manifest, patch_bytes, None)
    if manifest.get("candidate_id") != bundle_hash:
        errors.append(f"candidate_id mismatch in {cand_dir}")
    tmp_tar = tar_path + ".rebuild"
    write_deterministic_tar(tmp_tar, {"manifest.json": canon_bytes(manifest), "patch.diff": patch_bytes})
    if sha256_hex(open(tmp_tar, "rb").read()) != sha256_hex(open(tar_path, "rb").read()):
        errors.append(f"candidate.tar not deterministic in {cand_dir}")
    os.remove(tmp_tar)


def _load_devscreen_records(epoch_dir: str) -> Dict[str, Dict]:
    dev_root = os.path.join(epoch_dir, "devscreen")
    records: Dict[str, Dict] = {}
    if not os.path.isdir(dev_root):
        return records
    for name in sorted(os.listdir(dev_root)):
        if not name.startswith("candidate_"):
            continue
        cand_id = name.replace("candidate_", "")
        path = os.path.join(dev_root, name, "devscreen.json")
        if not os.path.exists(path):
            continue
        report = _read_json(path)
        records[cand_id] = report
    return records


def _load_apply_proof(cand_dir: str) -> Dict:
    path = os.path.join(cand_dir, "candidate_apply_proof.json")
    if not os.path.exists(path):
        return {}
    return _read_json(path)


def _load_filter_report(cand_dir: str) -> Dict:
    path = os.path.join(cand_dir, "filter_report.json")
    if not os.path.exists(path):
        return {}
    return _read_json(path)


def _load_baseline_distance(epoch_dir: str) -> Dict:
    path = os.path.join(epoch_dir, "baseline_devscreen.json")
    if not os.path.exists(path):
        return {"failing_tests": 0, "errors": 0}
    report = _read_json(path)
    return report.get("distance", {}) or {"failing_tests": 0, "errors": 0}


def replay_run(run_dir: str) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    run_manifest_path = os.path.join(run_dir, "run_manifest.json")
    run_config_path = os.path.join(run_dir, "run_config.json")
    scoreboard_path = os.path.join(run_dir, "scoreboard.json")
    sanity_path = os.path.join(run_dir, "sanity.json")
    improvement_path = os.path.join(run_dir, "improvement_curve.json")

    if not os.path.exists(run_manifest_path) or not os.path.exists(scoreboard_path):
        return False, ["missing run_manifest.json or scoreboard.json"]

    if os.path.exists(run_config_path) and not _is_canonical(run_config_path):
        errors.append("run_config.json not canonical")
    for path in (run_manifest_path, scoreboard_path, sanity_path, improvement_path):
        if os.path.exists(path) and not _is_canonical(path):
            errors.append(f"{os.path.basename(path)} not canonical")

    baseline_result = os.path.join(run_dir, "baseline", "baseline_sealed_dev_result.json")
    if os.path.exists(baseline_result) and not _is_canonical(baseline_result):
        errors.append("baseline_sealed_dev_result.json not canonical")

    epochs_dir = os.path.join(run_dir, "epochs")
    if not os.path.isdir(epochs_dir):
        return False, ["missing epochs directory"]

    for name in sorted(os.listdir(epochs_dir)):
        epoch_dir = os.path.join(epochs_dir, name)
        if not os.path.isdir(epoch_dir):
            continue
        summary_path = os.path.join(epoch_dir, "epoch_summary.json")
        if not os.path.exists(summary_path):
            return False, ["E_RUN_INCOMPLETE"]
        if not _is_canonical(summary_path):
            errors.append(f"epoch_summary.json not canonical in {name}")
        summary = _read_json(summary_path)
        status = str(summary.get("status", "COMPLETE"))
        if status != "COMPLETE":
            return False, ["E_RUN_INCOMPLETE"]

        baseline_path = os.path.join(epoch_dir, "baseline_devscreen.json")
        if not os.path.exists(baseline_path):
            errors.append(f"missing baseline_devscreen.json in {name}")
        elif not _is_canonical(baseline_path):
            errors.append(f"baseline_devscreen.json not canonical in {name}")
        rejections_path = os.path.join(epoch_dir, "rejections.json")
        if not os.path.exists(rejections_path):
            errors.append(f"missing rejections.json in {name}")
        elif not _is_canonical(rejections_path):
            errors.append(f"rejections.json not canonical in {name}")
        applicability_path = os.path.join(epoch_dir, "operator_applicability.json")
        if not os.path.exists(applicability_path):
            errors.append(f"missing operator_applicability.json in {name}")
        elif not _is_canonical(applicability_path):
            errors.append(f"operator_applicability.json not canonical in {name}")
        eval_set_path = os.path.join(epoch_dir, "devscreen_eval_set.json")
        if not os.path.exists(eval_set_path):
            errors.append(f"missing devscreen_eval_set.json in {name}")
        elif not _is_canonical(eval_set_path):
            errors.append(f"devscreen_eval_set.json not canonical in {name}")

        baseline_distance = _load_baseline_distance(epoch_dir)
        candidates_root = os.path.join(epoch_dir, "candidates")
        eligible_records: List[Dict] = []
        if os.path.isdir(candidates_root):
            for cand_id in sorted(os.listdir(candidates_root)):
                cand_dir = os.path.join(candidates_root, cand_id)
                proof_path = os.path.join(cand_dir, "candidate_apply_proof.json")
                if os.path.exists(proof_path) and not _is_canonical(proof_path):
                    errors.append(f"candidate_apply_proof.json not canonical in {name}/{cand_id}")
                filter_path = os.path.join(cand_dir, "filter_report.json")
                if not os.path.exists(filter_path):
                    errors.append(f"missing filter_report.json in {name}/{cand_id}")
                elif not _is_canonical(filter_path):
                    errors.append(f"filter_report.json not canonical in {name}/{cand_id}")
                filter_report = _load_filter_report(cand_dir)
                if not filter_report:
                    continue
                devscreen_ran = bool(filter_report.get("devscreen_ran"))
                if devscreen_ran:
                    dev_path = os.path.join(epoch_dir, "devscreen", f"candidate_{cand_id}", "devscreen.json")
                    if not os.path.exists(dev_path):
                        errors.append(f"missing devscreen.json for {name}/{cand_id}")
                        continue
                    if not _is_canonical(dev_path):
                        errors.append(f"devscreen.json not canonical in {name}/candidate_{cand_id}")
                        continue
                if not filter_report.get("eligible_for_sealed"):
                    continue
                patch_path = os.path.join(cand_dir, "patch.diff")
                patch_bytes = b""
                if os.path.exists(patch_path):
                    patch_bytes = open(patch_path, "rb").read()
                eligible_records.append(
                    {
                        "candidate_id": cand_id,
                        "devscreen_ok": bool(filter_report.get("devscreen_ok")),
                        "distance": filter_report.get("candidate_distance", {}),
                        "patch_bytes": int(len(patch_bytes)),
                    }
                )

        topk_n = int(summary.get("topk_submitted", 0))
        topk, ranked_all = select_topk_for_submission(eligible_records, baseline_distance, topk_n)
        recomputed_ranked = [r.get("candidate_id", "") for r in ranked_all if r.get("candidate_id")]
        recomputed_topk = [r.get("candidate_id", "") for r in topk if r.get("candidate_id")]
        stored_topk = summary.get("topk_candidate_ids", [])
        stored_ranked = summary.get("ranked_candidate_ids", [])
        if list(stored_ranked) != list(recomputed_ranked):
            errors.append(f"ranked_candidate_ids mismatch in {name}")
        if list(stored_topk) != list(recomputed_topk):
            errors.append(f"topk mismatch in {name}")

        # Canonical sealed results and promotion report
        for sealed_dir in ("sealed_dev", "sealed_heldout"):
            base = os.path.join(epoch_dir, sealed_dir)
            if os.path.isdir(base):
                for dname in sorted(os.listdir(base)):
                    sealed_path = os.path.join(base, dname, "sealed_result.json")
                    if os.path.exists(sealed_path) and not _is_canonical(sealed_path):
                        errors.append(f"sealed_result.json not canonical in {name}/{sealed_dir}/{dname}")
                promo_path = os.path.join(base, "promotion_report.json")
                if os.path.exists(promo_path) and not _is_canonical(promo_path):
                    errors.append(f"promotion_report.json not canonical in {name}/{sealed_dir}")

        controls_path = os.path.join(epoch_dir, "controls", "null_control_sealed_dev_result.json")
        if os.path.exists(controls_path) and not _is_canonical(controls_path):
            errors.append(f"null_control_sealed_dev_result.json not canonical in {name}")

        # Candidate tar determinism
        if os.path.isdir(candidates_root):
            for cand_id in sorted(os.listdir(candidates_root)):
                _verify_candidate_tar(os.path.join(candidates_root, cand_id), errors)

    return len(errors) == 0, errors


def verify_run(run_dir: str) -> Tuple[bool, List[str]]:
    return replay_run(run_dir)


__all__ = ["replay_run", "verify_run"]
