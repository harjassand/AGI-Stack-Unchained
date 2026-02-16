"""Verifier for RSI demon v6 efficiency attempts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from ..v1_8r.metabolism_v1.translation import evaluate_translation
from ..v1_8r.metabolism_v1.workvec import WorkVec
from .autonomy import compute_expected, load_translation_inputs
from .constants import require_constants
from .efficiency import efficiency_gate


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _latest_report(dir_path: Path, prefix: str) -> dict[str, Any]:
    if not dir_path.exists():
        _fail("EFFICIENCY_REPORT_DERIVATION_MISMATCH")
    best_epoch = None
    best_path = None
    for report_path in dir_path.glob(f"{prefix}_epoch_*.json"):
        tail = report_path.stem.split("_epoch_")[-1]
        if not tail.isdigit():
            continue
        idx = int(tail)
        if best_epoch is None or idx > best_epoch:
            best_epoch = idx
            best_path = report_path
    if best_path is None:
        _fail("EFFICIENCY_REPORT_DERIVATION_MISMATCH")
    return load_canon_json(best_path)


def _verify_campaign_pack(state_dir: Path) -> dict[str, Any]:
    pinned_path = state_dir / "current" / "campaign_pack" / "campaign_pack_used.json"
    if not pinned_path.exists():
        _fail("CAMPAIGN_PACK_NOT_PINNED")
    pinned = load_canon_json(pinned_path)
    if pinned.get("schema") != "rsi_real_demon_campaign_pack_v6" or int(pinned.get("schema_version", 0)) != 6:
        _fail("CAMPAIGN_PACK_NOT_PINNED")

    source_path = _repo_root() / "campaigns" / "rsi_real_demon_v6_efficiency" / "rsi_real_demon_campaign_pack_v6.json"
    if not source_path.exists():
        _fail("CAMPAIGN_PACK_NOT_PINNED")
    source = load_canon_json(source_path)
    if source.get("schema") != "rsi_real_demon_campaign_pack_v6" or int(source.get("schema_version", 0)) != 6:
        _fail("CAMPAIGN_PACK_NOT_PINNED")

    if sha256_prefixed(canon_bytes(pinned)) != sha256_prefixed(canon_bytes(source)):
        _fail("CAMPAIGN_PACK_NOT_PINNED")

    proposals = source.get("proposals") if isinstance(source.get("proposals"), dict) else None
    autonomy = source.get("autonomy") if isinstance(source.get("autonomy"), dict) else None
    metabolism = autonomy.get("metabolism") if isinstance(autonomy, dict) else None

    if not isinstance(proposals, dict):
        _fail("AUTONOMY_V2_CHECK_FAIL")
    if proposals.get("metabolism_v1_dir") != "__AUTONOMY_RUNDIR_V2__":
        _fail("AUTONOMY_V2_CHECK_FAIL")
    if not isinstance(autonomy, dict) or not autonomy.get("enabled"):
        _fail("AUTONOMY_V2_CHECK_FAIL")
    if not isinstance(metabolism, dict):
        _fail("AUTONOMY_V2_CHECK_FAIL")
    if metabolism.get("algorithm") != "autopatch_enum_v2":
        _fail("AUTONOMY_V2_CHECK_FAIL")
    if metabolism.get("manifest_rundir_path") != "autonomy/metabolism_v1/autonomy_manifest_v2.json":
        _fail("AUTONOMY_V2_CHECK_FAIL")
    if metabolism.get("proposals_rundir_subdir") != "autonomy/metabolism_v1/proposals":
        _fail("AUTONOMY_V2_CHECK_FAIL")

    return source


def _validate_manifest(manifest: dict[str, Any]) -> None:
    required_keys = {
        "schema",
        "schema_version",
        "autonomy_kind",
        "algorithm",
        "attempt_index",
        "prior_attempt_index",
        "prior_verifier_reason",
        "translation_inputs_hash",
        "constants_hash",
        "output_subdir",
        "patches",
        "x-meta",
    }
    if set(manifest.keys()) != required_keys:
        _fail("AUTONOMY_V2_CHECK_FAIL")
    if manifest.get("schema") != "autonomy_manifest_v2" or int(manifest.get("schema_version", 0)) != 2:
        _fail("AUTONOMY_V2_CHECK_FAIL")
    if manifest.get("autonomy_kind") != "metabolism_autonomy_v2":
        _fail("AUTONOMY_V2_CHECK_FAIL")
    if manifest.get("algorithm") != "autopatch_enum_v2":
        _fail("AUTONOMY_V2_CHECK_FAIL")
    if manifest.get("output_subdir") != "autonomy/metabolism_v1/proposals":
        _fail("AUTONOMY_V2_CHECK_FAIL")
    if not isinstance(manifest.get("patches"), list) or len(manifest.get("patches")) != 1:
        _fail("AUTONOMY_V2_CHECK_FAIL")
    xmeta = manifest.get("x-meta")
    if not isinstance(xmeta, dict) or set(xmeta.keys()) != {"KERNEL_HASH", "META_HASH"}:
        _fail("AUTONOMY_V2_CHECK_FAIL")

    patches = manifest.get("patches")
    prev_hash = None
    seen = set()
    for entry in patches:
        if not isinstance(entry, dict):
            _fail("AUTONOMY_V2_CHECK_FAIL")
        if set(entry.keys()) != {"patch_id", "patch_def_hash", "patch_kind", "params"}:
            _fail("AUTONOMY_V2_CHECK_FAIL")
        if entry.get("patch_kind") != "ctx_hash_cache_v1":
            _fail("AUTONOMY_V2_CHECK_FAIL")
        params = entry.get("params")
        if not isinstance(params, dict) or set(params.keys()) != {"capacity"}:
            _fail("AUTONOMY_V2_CHECK_FAIL")
        patch_def_hash = entry.get("patch_def_hash")
        if not isinstance(patch_def_hash, str):
            _fail("AUTONOMY_V2_CHECK_FAIL")
        if patch_def_hash in seen:
            _fail("AUTONOMY_V2_CHECK_FAIL")
        seen.add(patch_def_hash)
        if prev_hash is not None and patch_def_hash < prev_hash:
            _fail("AUTONOMY_V2_CHECK_FAIL")
        prev_hash = patch_def_hash


def _verify_autonomy(state_dir: Path, campaign_pack: dict[str, Any]) -> dict[str, Any]:
    manifest_path = state_dir / "autonomy" / "metabolism_v1" / "autonomy_manifest_v2.json"
    if not manifest_path.exists():
        _fail("AUTONOMY_V2_CHECK_FAIL")
    manifest = load_canon_json(manifest_path)
    _validate_manifest(manifest)

    translation_cfg = campaign_pack.get("translation") if isinstance(campaign_pack.get("translation"), dict) else None
    translation_path = translation_cfg.get("translation_inputs_path") if isinstance(translation_cfg, dict) else None
    if not isinstance(translation_path, str):
        _fail("AUTONOMY_V2_CHECK_FAIL")
    translation_inputs = load_translation_inputs(
        _repo_root() / "campaigns" / "rsi_real_demon_v6_efficiency" / translation_path
    )

    expected_manifest, expected_patch_defs = compute_expected(
        translation_inputs,
        attempt_index=int(manifest.get("attempt_index", 0)),
        prior_attempt_index=int(manifest.get("prior_attempt_index", 0)),
        prior_verifier_reason=str(manifest.get("prior_verifier_reason", "")),
    )

    if manifest.get("translation_inputs_hash") != expected_manifest.get("translation_inputs_hash"):
        _fail("AUTONOMY_V2_CHECK_FAIL")
    if manifest.get("constants_hash") != expected_manifest.get("constants_hash"):
        _fail("AUTONOMY_V2_CHECK_FAIL")

    if manifest.get("patches") != expected_manifest.get("patches"):
        _fail("AUTONOMY_V2_CHECK_FAIL")

    proposals_dir = state_dir / "autonomy" / "metabolism_v1" / "proposals"
    if not proposals_dir.exists():
        _fail("AUTONOMY_V2_CHECK_FAIL")
    actual_hashes: list[str] = []
    for path in proposals_dir.glob("*.json"):
        payload = load_canon_json(path)
        actual_hashes.append(sha256_prefixed(canon_bytes(payload)))
    actual_hashes.sort()
    expected_hashes = [entry.get("patch_def_hash") for entry in manifest.get("patches", [])]
    if actual_hashes != expected_hashes:
        _fail("AUTONOMY_V2_CHECK_FAIL")

    expected_by_hash = {sha256_prefixed(canon_bytes(patch)): patch for patch in expected_patch_defs}
    for path in sorted(proposals_dir.glob("*.json")):
        payload = load_canon_json(path)
        patch_hash = sha256_prefixed(canon_bytes(payload))
        expected = expected_by_hash.get(patch_hash)
        if expected is None or payload != expected:
            _fail("AUTONOMY_V2_CHECK_FAIL")

    return manifest


def _validate_report(report: dict[str, Any]) -> None:
    required = {
        "schema",
        "schema_version",
        "epoch",
        "workvec_base",
        "workvec_patch",
        "work_cost_base",
        "work_cost_patch",
        "rho_met",
        "rho_met_min",
        "efficiency_vector_dominance",
        "efficiency_scalar_gate",
        "efficiency_gate_passed",
    }
    if set(report.keys()) != required:
        _fail("EFFICIENCY_REPORT_DERIVATION_MISMATCH")
    if report.get("schema") != "meta_patch_eval_report_v2" or int(report.get("schema_version", 0)) != 2:
        _fail("EFFICIENCY_REPORT_DERIVATION_MISMATCH")


def _hash_workvec(workvec: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(workvec))


def _verify_efficiency(state_dir: Path, manifest: dict[str, Any], campaign_pack: dict[str, Any]) -> dict[str, Any]:
    metabolism_root = state_dir / "current" / "metabolism_v1"
    report = _latest_report(metabolism_root / "reports", "meta_patch_eval_report_v2")
    _validate_report(report)

    translation_cfg = campaign_pack.get("translation") if isinstance(campaign_pack.get("translation"), dict) else None
    translation_path = translation_cfg.get("translation_inputs_path") if isinstance(translation_cfg, dict) else None
    if not isinstance(translation_path, str):
        _fail("AUTONOMY_V2_CHECK_FAIL")
    translation_inputs = load_translation_inputs(
        _repo_root() / "campaigns" / "rsi_real_demon_v6_efficiency" / translation_path
    )

    proposals_dir = state_dir / "autonomy" / "metabolism_v1" / "proposals"
    patch_entry = manifest.get("patches")[0]
    patch_def_hash = patch_entry.get("patch_def_hash")
    patch_def_path = None
    for path in proposals_dir.glob("*.json"):
        payload = load_canon_json(path)
        if sha256_prefixed(canon_bytes(payload)) == patch_def_hash:
            patch_def_path = path
            break
    if patch_def_path is None:
        _fail("AUTONOMY_V2_CHECK_FAIL")

    patch_def = load_canon_json(patch_def_path)
    capacity = int(patch_def.get("params", {}).get("capacity", 0))

    eval_result = evaluate_translation(
        translation_inputs=translation_inputs,
        cache_capacity=capacity,
        min_sha256_delta=0,
    )
    workvec_base: WorkVec = eval_result.get("workvec_base")
    workvec_patch: WorkVec = eval_result.get("workvec_patch")

    constants = require_constants()
    weights = constants.get("WORK_COST_WEIGHTS_V1", {}) if isinstance(constants.get("WORK_COST_WEIGHTS_V1"), dict) else {}
    rho_min_num = int(constants.get("RHO_MET_MIN_NUM", 0) or 0)
    rho_min_den = int(constants.get("RHO_MET_MIN_DEN", 1) or 1)

    gate_info = efficiency_gate(
        workvec_base,
        workvec_patch,
        weights=weights,
        rho_min_num=rho_min_num,
        rho_min_den=rho_min_den,
    )

    stored_base = report.get("workvec_base")
    stored_patch = report.get("workvec_patch")
    if not isinstance(stored_base, dict) or not isinstance(stored_patch, dict):
        _fail("EFFICIENCY_REPORT_DERIVATION_MISMATCH")

    if _hash_workvec(stored_base) != _hash_workvec(workvec_base.to_dict()):
        _fail("EFFICIENCY_WORKVEC_REPLAY_MISMATCH")
    if _hash_workvec(stored_patch) != _hash_workvec(workvec_patch.to_dict()):
        _fail("EFFICIENCY_WORKVEC_REPLAY_MISMATCH")

    if int(report.get("work_cost_base", -1)) != int(gate_info.get("work_cost_base", -2)):
        _fail("EFFICIENCY_REPORT_DERIVATION_MISMATCH")
    if int(report.get("work_cost_patch", -1)) != int(gate_info.get("work_cost_patch", -2)):
        _fail("EFFICIENCY_REPORT_DERIVATION_MISMATCH")
    if report.get("rho_met") != gate_info.get("rho_met"):
        _fail("EFFICIENCY_REPORT_DERIVATION_MISMATCH")
    if report.get("rho_met_min") != {"num": rho_min_num, "den": rho_min_den}:
        _fail("EFFICIENCY_REPORT_DERIVATION_MISMATCH")
    if bool(report.get("efficiency_vector_dominance")) != bool(gate_info.get("efficiency_vector_dominance")):
        _fail("EFFICIENCY_REPORT_DERIVATION_MISMATCH")
    if bool(report.get("efficiency_scalar_gate")) != bool(gate_info.get("efficiency_scalar_gate")):
        _fail("EFFICIENCY_REPORT_DERIVATION_MISMATCH")
    if bool(report.get("efficiency_gate_passed")) != bool(gate_info.get("efficiency_gate_passed")):
        _fail("EFFICIENCY_REPORT_DERIVATION_MISMATCH")

    if not bool(gate_info.get("efficiency_gate_passed")):
        _fail("EFFICIENCY_GATE_FAIL")

    return report


def _verify_receipt(state_dir: Path, report: dict[str, Any], campaign_pack: dict[str, Any]) -> None:
    final_epoch = int(campaign_pack.get("epochs", 0) or 0)
    receipt_path = state_dir / "epochs" / f"epoch_{final_epoch}" / "diagnostics" / "rsi_demon_receipt_v6.json"
    if not receipt_path.exists():
        _fail("RECEIPT_MISMATCH_V6")
    receipt = load_canon_json(receipt_path)
    if receipt.get("schema") != "rsi_demon_receipt_v6":
        _fail("RECEIPT_MISMATCH_V6")
    if int(receipt.get("schema_version", 0)) != 6:
        _fail("RECEIPT_MISMATCH_V6")

    metab = receipt.get("metabolism_v1") if isinstance(receipt.get("metabolism_v1"), dict) else None
    if not isinstance(metab, dict):
        _fail("RECEIPT_MISMATCH_V6")

    if int(metab.get("latest_eval_epoch", -1)) != int(report.get("epoch", -2)):
        _fail("RECEIPT_MISMATCH_V6")
    if int(metab.get("work_cost_base", -1)) != int(report.get("work_cost_base", -2)):
        _fail("RECEIPT_MISMATCH_V6")
    if int(metab.get("work_cost_patch", -1)) != int(report.get("work_cost_patch", -2)):
        _fail("RECEIPT_MISMATCH_V6")
    if metab.get("rho_met") != report.get("rho_met"):
        _fail("RECEIPT_MISMATCH_V6")
    if metab.get("rho_coupled") != report.get("rho_met"):
        _fail("RECEIPT_MISMATCH_V6")
    if bool(metab.get("efficiency_gate_passed")) != bool(report.get("efficiency_gate_passed")):
        _fail("RECEIPT_MISMATCH_V6")

    verdict = receipt.get("verdict")
    if bool(report.get("efficiency_gate_passed")):
        if verdict != "VALID":
            _fail("RECEIPT_MISMATCH_V6")
        if int(metab.get("activated", 0)) < 1:
            _fail("RECEIPT_MISMATCH_V6")
    else:
        if verdict != "INVALID":
            _fail("RECEIPT_MISMATCH_V6")
        if int(metab.get("activated", 0)) != 0:
            _fail("RECEIPT_MISMATCH_V6")


def verify(state_dir: Path) -> None:
    campaign_pack = _verify_campaign_pack(state_dir)
    manifest = _verify_autonomy(state_dir, campaign_pack)
    report = _verify_efficiency(state_dir, manifest, campaign_pack)
    _verify_receipt(state_dir, report, campaign_pack)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify RSI demon v6 efficiency attempt")
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()
    try:
        verify(Path(args.state_dir))
    except Exception as exc:  # noqa: BLE001
        reason = str(exc) if str(exc) else "unknown"
        print(f"INVALID: {reason}")
        return
    print("VALID")


if __name__ == "__main__":
    main()
