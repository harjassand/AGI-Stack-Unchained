"""CLI entrypoint for CAOE v1 proposer."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tarfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[1]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from api_v1 import bootstrap_paths, load_json, write_json  # noqa: E402
from artifacts.candidate_manifest_builder_v1 import build_manifest  # noqa: E402
from artifacts.candidate_tar_writer_v1 import build_candidate_tar_bytes  # noqa: E402
from artifacts.candidate_manifest_builder_v1 import extract_suite_id  # noqa: E402
from artifacts.ids_v1 import mechanism_hash, ontology_hash  # noqa: E402
from dawn.cdel_client_v1 import run_cdel_verify  # noqa: E402
from dawn.evidence_parser_v1 import parse_evidence_report  # noqa: E402
from dawn.learner_v1 import update_state  # noqa: E402
from dawn.monitor_falsifiers_v1 import compute_flags  # noqa: E402
from dawn.nuisance_classification_v1_2 import classify_nuisance_rate_scale  # noqa: E402
from dawn.selector_v1 import select_candidate  # noqa: E402
from sleep.absop_isa_v1_2 import operator_rankings, propose_candidates_with_stats  # noqa: E402
from sleep.synth.patch_synthesizer_v1 import synthesize_candidates  # noqa: E402
from state.proposer_state_store_v1 import load_state, save_state  # noqa: E402
from wake.dev_diagnostics_v1_2 import compute_episode_successes  # noqa: E402
from wake.wake_anomaly_miner_v1 import run_identity_and_mine  # noqa: E402


def _write_text_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _sha256_hex_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_hex_file(path: Path) -> str:
    return _sha256_hex_bytes(path.read_bytes())


def _write_sha256(path: Path, hex_digest: str) -> None:
    path.write_text(f"{hex_digest}\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_ontology_patch(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    if patch.get("base_ontology_hash") != ontology_hash(base):
        raise ValueError("base_ontology_hash mismatch")
    if "isa_version" in patch and patch.get("isa_version") != base.get("isa_version"):
        raise ValueError("isa_version mismatch")
    ops = patch.get("ops") or []
    out = json.loads(json.dumps(base))
    for op in ops:
        kind = op.get("op")
        if kind == "add_symbol":
            out["symbols"].append(op["symbol"])
        elif kind == "remove_symbol":
            name = op["name"]
            out["symbols"] = [s for s in out["symbols"] if s["name"] != name]
        elif kind == "replace_phi":
            out["measurement_phi"] = op["phi"]
        elif kind == "replace_lambda":
            out["lowering_lambda"] = op["lambda"]
        elif kind == "set_supports_macro_do":
            out["supports_macro_do"] = op["value"]
            if not op["value"]:
                out["lifting_psi"] = None
        elif kind == "set_supports_repeat_action_options":
            out["supports_repeat_action_options"] = op["value"]
        elif kind == "replace_psi":
            out["lifting_psi"] = op["psi"]
        elif kind == "set_complexity_limits":
            out["complexity_limits"] = op["limits"]
        else:
            raise ValueError("unknown patch op")
    out["symbols"] = sorted(out.get("symbols") or [], key=lambda s: s["name"])
    return out


def _apply_mech_diff(base: dict[str, Any], diff: dict[str, Any]) -> dict[str, Any]:
    if not diff:
        return json.loads(json.dumps(base))
    if diff.get("base_mech_hash") != mechanism_hash(base):
        raise ValueError("base_mech_hash mismatch")
    out = json.loads(json.dumps(base))
    ops = diff.get("ops") or []
    mech_map = {m["mechanism_id"]: m for m in out.get("mechanisms") or []}
    for op in ops:
        kind = op.get("op")
        if kind == "add_mechanism":
            mech = op["mechanism"]
            mech_map[mech["mechanism_id"]] = mech
        elif kind == "remove_mechanism":
            mech_map.pop(op["mechanism_id"], None)
        elif kind == "replace_mechanism":
            mech = op["mechanism"]
            mech_map[mech["mechanism_id"]] = mech
        elif kind == "set_mechanism_params":
            mech_id = op["mechanism_id"]
            mech = mech_map.get(mech_id)
            if mech is None:
                raise ValueError("mechanism not found for param update")
            mech = json.loads(json.dumps(mech))
            mech["params"] = op["params"]
            mech_map[mech_id] = mech
        else:
            raise ValueError("unknown mech diff op")
    out["mechanisms"] = sorted(mech_map.values(), key=lambda m: m["mechanism_id"])
    return out


def _write_atomic(path: Path, data: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    _write_text_json(tmp_path, data)
    os.replace(tmp_path, path)


def _operator_name(op_id: str) -> str:
    mapping = {
        "ABSOP_COARSE_GRAIN_MERGE_V1": "coarse_grain_merge",
        "ABSOP_LATENT_REIFY_V1": "latent_reify",
        "ABSOP_TEMPLATE_EXTRACT_V1": "template_extract",
        "ABSOP_OPTION_COMPILE_V1": "option_compile",
        "ABSOP_OPTION_COMPILE_V1_1": "option_compile_v1_1",
        "ABSOP_STABILITY_LATENT_DETECT_V1_1": "stability_latent_detect",
        "ABSOP_EFE_TUNE_V1_1": "efe_tune",
        "ABSOP_RENDER_CANONICALIZE_PHI_V1_1": "render_canonicalize_phi",
        "ABSOP_RATE_SCALE_REPEAT_OPTION_V1_2": "rate_scale_repeat_option",
        "ABSOP_TEMPORAL_DENOISE_PHI_V1_2": "temporal_denoise_phi",
        "ABSOP_HYSTERESIS_FILTER_V1_2": "hysteresis_filter",
        "IDENTITY": "identity",
    }
    return mapping.get(op_id, str(op_id))


def _avg_success(per_regime_success: dict[str, float]) -> float:
    if not per_regime_success:
        return 0.0
    return sum(float(v) for v in per_regime_success.values()) / len(per_regime_success)


def _min_success(per_regime_success: dict[str, float]) -> float:
    if not per_regime_success:
        return 0.0
    values = [float(v) for v in per_regime_success.values()]
    return min(values) if values else 0.0


def _load_optional_json(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        return load_json(path)
    except Exception:
        return None


def _candidate_patch(candidate: dict[str, Any]) -> dict[str, Any] | None:
    patch = candidate.get("ontology_patch")
    if isinstance(patch, dict):
        return patch
    tar_bytes = candidate.get("tar_bytes")
    if not isinstance(tar_bytes, (bytes, bytearray)):
        return None
    try:
        with tarfile.open(fileobj=io.BytesIO(bytes(tar_bytes)), mode="r:*") as tf:
            entry = tf.extractfile("ontology_patch.json")
            if entry is None:
                return None
            return json.loads(entry.read().decode("utf-8"))
    except Exception:
        return None


def _candidate_ontology_for_gate(
    candidate: dict[str, Any],
    base_ontology: dict[str, Any],
) -> dict[str, Any] | None:
    patch = _candidate_patch(candidate)
    if patch is None:
        return base_ontology
    try:
        return _apply_ontology_patch(base_ontology, patch)
    except Exception:
        return None


def _nuisance_k2_episodes(suitepack_dev: dict[str, Any]) -> list[dict[str, Any]]:
    episodes = suitepack_dev.get("episodes") if isinstance(suitepack_dev, dict) else None
    if not isinstance(episodes, list):
        return []
    selected: list[dict[str, Any]] = []
    for ep in episodes:
        if not isinstance(ep, dict):
            continue
        regime_id = str(ep.get("regime_id") or ep.get("regime") or "")
        if regime_id.startswith("nuisance_k2"):
            selected.append(ep)
    return selected


def _augment_nuisance_k2_gate(episodes: list[dict[str, Any]], seeds: list[int]) -> list[dict[str, Any]]:
    if not episodes:
        return []
    if len(episodes) >= 3:
        out = []
        for ep in episodes:
            seed_val = ep.get("seed")
            if seed_val is None:
                seed_val = ep.get("episode_seed")
            out.append(
                {
                    "episode_id": str(ep.get("episode_id") or ""),
                    "regime_id": str(ep.get("regime_id") or ep.get("regime") or ""),
                    "seed": int(seed_val) if seed_val is not None else 0,
                    "source_episode_id": str(ep.get("episode_id") or ""),
                }
            )
        return out
    base = episodes[0]
    base_id = str(base.get("episode_id") or "")
    base_regime = str(base.get("regime_id") or base.get("regime") or "")
    out = []
    for seed in seeds:
        out.append(
            {
                "episode_id": base_id,
                "regime_id": base_regime,
                "seed": int(seed),
                "source_episode_id": base_id,
            }
        )
    return out


def _nuisance_family_present(anomaly_buffer: dict[str, Any]) -> bool:
    worst_regimes = anomaly_buffer.get("signals", {}).get("worst_regimes", [])
    for item in worst_regimes:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("regime_id") or "")
        if rid.startswith("nuisance_k2") or rid.startswith("nuisance"):
            return True
    worst_families = anomaly_buffer.get("signals", {}).get("worst_families", [])
    for item in worst_families:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("family_id") or "")
        if fid.startswith("nuisance_rate_scale") or fid.startswith("nuisance"):
            return True
    return False


def _candidate_budgets(
    *,
    anomaly_buffer: dict[str, Any],
    dev_classification: dict[str, Any] | None,
) -> tuple[dict[str, int], dict[str, int], dict[str, Any]]:
    min_by_op = {
        "ABSOP_RENDER_CANONICALIZE_PHI_V1_1": 8,
        "ABSOP_EFE_TUNE_V1_1": 8,
        "ABSOP_TEMPLATE_EXTRACT_V1": 4,
        "ABSOP_OPTION_COMPILE_V1_1": 2,
    }
    max_by_op = {"ABSOP_EFE_TUNE_V1_1": 8}
    budget_by_family: dict[str, Any] = {}
    if _nuisance_family_present(anomaly_buffer):
        label = "UNKNOWN"
        unsolvable = False
        if isinstance(dev_classification, dict):
            label = str(dev_classification.get("label") or "UNKNOWN")
            unsolvable = bool(dev_classification.get("unsolvable"))
        target_op = None
        if not unsolvable:
            if label == "TIME_SCALE":
                target_op = "ABSOP_RATE_SCALE_REPEAT_OPTION_V1_2"
            elif label == "OBS_NOISE":
                target_op = "ABSOP_TEMPORAL_DENOISE_PHI_V1_2"
            elif label == "MEMORY_REQUIRED":
                target_op = "ABSOP_HYSTERESIS_FILTER_V1_2"
            else:
                for op_id in (
                    "ABSOP_RATE_SCALE_REPEAT_OPTION_V1_2",
                    "ABSOP_TEMPORAL_DENOISE_PHI_V1_2",
                    "ABSOP_HYSTERESIS_FILTER_V1_2",
                ):
                    min_by_op[op_id] = 8
        if target_op:
            min_by_op[target_op] = 24
        budget_by_family["nuisance_rate_scale"] = {
            "classification": label,
            "unsolvable": bool(unsolvable),
            "target_operator": target_op or "MIXED",
            "target_budget": 24,
        }
    return min_by_op, max_by_op, budget_by_family


def _load_intervention_logs(
    report: dict[str, Any],
    evidence_dir: Path | None,
    *,
    suite_track: str,
    variant: str,
) -> list[dict[str, Any]]:
    if evidence_dir is None:
        return []
    logs: list[dict[str, Any]] = []
    refs = (report.get("artifacts") or {}).get("intervention_logs") or []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        if ref.get("suite_track") != suite_track or ref.get("variant") != variant:
            continue
        rel = ref.get("relative_path")
        if not rel:
            continue
        path = evidence_dir / str(rel)
        if not path.exists():
            continue
        try:
            logs.append(load_json(path))
        except Exception:
            continue
    return logs


def _candidate_phi_program(
    candidate: dict[str, Any],
    base_ontology: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    patch = candidate.get("ontology_patch") or {}
    for op in patch.get("ops") or []:
        if op.get("op") == "replace_phi" and isinstance(op.get("phi"), dict):
            return op["phi"], True
    return base_ontology.get("measurement_phi") or {}, False


def _phi_input_name_used(phi_prog: dict[str, Any]) -> str:
    inputs = phi_prog.get("inputs") or []
    first_name = ""
    for decl in inputs:
        name = decl.get("name")
        if not isinstance(name, str):
            continue
        if not first_name:
            first_name = name
        if name.startswith("o_t_canon_"):
            return name
    return first_name or "unknown"


def _phi_operator_id_used(op_id: str, phi_input_name: str, replaced: bool) -> str:
    if phi_input_name.startswith("o_t_canon_"):
        return "ABSOP_RENDER_CANONICALIZE_PHI_V1_1"
    if replaced:
        return op_id or "REPLACE_PHI_OTHER"
    return "BASE"


def _regression_guard_failure(
    base_success_map: dict[str, float],
    candidate_success_map: dict[str, float],
) -> bool:
    for rid, base_val in base_success_map.items():
        try:
            cand_val = float(candidate_success_map.get(rid, 0.0))
        except (TypeError, ValueError):
            cand_val = 0.0
        if float(base_val) >= 1.0 and cand_val < float(base_val):
            return True
    return False


def _augment_phi_debug_files(
    candidate_id: str,
    proposal_type: str,
    operator_id: str,
    phi_input_name: str,
    evidence_dir: Path | None,
) -> None:
    if evidence_dir is None:
        return
    phi_root = evidence_dir / "phi_debug"
    if not phi_root.exists():
        return
    for debug_path in phi_root.rglob("phi_debug.json"):
        try:
            payload = load_json(debug_path)
        except Exception:
            continue
        payload["proposal_type"] = proposal_type
        payload["operator_id"] = operator_id
        payload["phi_input_name_used"] = phi_input_name
        _write_text_json(debug_path, payload)
        _write_sha256(debug_path.parent / "phi_debug.sha256", _sha256_hex_file(debug_path))


def _summarize_ontology_ops(ops: list[dict[str, Any]]) -> list[str]:
    summaries: list[str] = []
    for op in ops:
        kind = op.get("op")
        if kind == "add_symbol":
            name = op.get("symbol", {}).get("name", "unknown")
            summaries.append(f"add_symbol:{name}")
        elif kind == "remove_symbol":
            summaries.append(f"remove_symbol:{op.get('name', 'unknown')}")
        elif kind == "replace_phi":
            summaries.append("replace_phi")
        elif kind == "replace_lambda":
            summaries.append("replace_lambda")
        elif kind == "replace_psi":
            summaries.append("replace_psi")
        elif kind == "set_supports_macro_do":
            summaries.append(f"set_supports_macro_do:{bool(op.get('value'))}")
        elif kind == "set_supports_repeat_action_options":
            summaries.append(f"set_supports_repeat_action_options:{bool(op.get('value'))}")
        elif kind == "set_complexity_limits":
            limits = op.get("limits") or {}
            summaries.append(
                "set_complexity_limits:"
                f"phi_max_ops={limits.get('phi_max_ops')},"
                f"lambda_max_ops={limits.get('lambda_max_ops')},"
                f"psi_max_ops={limits.get('psi_max_ops')},"
                f"max_constants={limits.get('max_constants')},"
                f"max_state_history={limits.get('max_state_history')}"
            )
        else:
            summaries.append(str(kind or "unknown"))
    return summaries


def _summarize_mech_ops(ops: list[dict[str, Any]]) -> list[str]:
    summaries: list[str] = []
    for op in ops:
        kind = op.get("op")
        if kind in {"add_mechanism", "replace_mechanism"}:
            mech = op.get("mechanism") or {}
            mech_id = mech.get("mechanism_id", "unknown")
            params = mech.get("params") or {}
            if params:
                param_items = ",".join(f"{k}={params[k]}" for k in sorted(params.keys()))
                summaries.append(f"{kind}:{mech_id}:{param_items}")
            else:
                summaries.append(f"{kind}:{mech_id}")
        elif kind == "remove_mechanism":
            summaries.append(f"remove_mechanism:{op.get('mechanism_id', 'unknown')}")
        else:
            summaries.append(str(kind or "unknown"))
    return summaries


def _floor_diagnostic_from_report(report: dict[str, Any]) -> dict[str, Any]:
    base_inv = (report.get("base_metrics") or {}).get("c_inv") or {}
    cand_inv = (report.get("candidate_metrics") or {}).get("c_inv") or {}
    base_per_regime = base_inv.get("per_regime_success") or {}
    cand_per_regime = cand_inv.get("per_regime_success") or {}
    base_zero = sorted([rid for rid, val in base_per_regime.items() if float(val) == 0.0])
    cand_zero = sorted([rid for rid, val in cand_per_regime.items() if float(val) == 0.0])
    base_zero_set = set(base_zero)
    cand_zero_set = set(cand_zero)
    return {
        "base_zero_regimes": base_zero,
        "candidate_zero_regimes": cand_zero,
        "zero_intersection": sorted(base_zero_set & cand_zero_set),
        "zero_symmetric_diff": sorted(base_zero_set ^ cand_zero_set),
        "base_per_family": base_inv.get("per_family") or {},
        "candidate_per_family": cand_inv.get("per_family") or {},
    }


def _contract_result(contract: dict[str, Any] | None) -> str:
    if not contract:
        return "FAIL"
    return "PASS" if contract.get("pass") is True else "FAIL"


def _primary_reason_code(reason_codes: list[str]) -> str:
    priority = [
        "FORMAT_ERROR",
        "NO_EVIDENCE",
        "SCREEN_ONLY",
        "FAIL_DEV_NUISANCE_GATE",
        "FAIL_REGRESSION_GUARD",
        "FAIL_C_ANTI",
        "FAIL_C_DO",
        "FAIL_C_MDL",
        "FAIL_C_INV",
        "FAIL_C_LIFE",
    ]
    for code in priority:
        if code in reason_codes:
            return code
    return reason_codes[0] if reason_codes else "NONE"


def _episode_regime_id(episode: dict[str, Any]) -> str:
    return str(episode.get("regime_id") or episode.get("regime") or "")


def _suitepack_episode_counts(suitepack: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ep in suitepack.get("episodes") or []:
        rid = _episode_regime_id(ep)
        if not rid:
            continue
        counts[rid] = counts.get(rid, 0) + 1
    return counts


def _load_selection(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _collect_evaluations(candidates: list[dict[str, Any]], cdel_results_dir: Path) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    for idx, cand in enumerate(candidates):
        evidence_path = cdel_results_dir / f"candidate_{idx}" / "evidence_report.json"
        if not evidence_path.exists():
            raise RuntimeError(f"missing evidence_report.json for candidate_{idx}")
        parsed = parse_evidence_report(evidence_path)
        parsed["op_id"] = cand.get("op_id")
        parsed["candidate_index"] = idx
        evaluations.append(parsed)
    return evaluations


def _build_identity_candidate(
    *,
    base_ontology: dict[str, Any],
    base_mech: dict[str, Any],
    suite_id_dev: str,
    suite_id_heldout: str,
) -> dict[str, Any]:
    patch = {
        "format": "ontology_patch_v1_1",
        "schema_version": 1,
        "base_ontology_hash": ontology_hash(base_ontology),
        "isa_version": str(base_ontology.get("isa_version") or "caoe_absop_isa_v1_2"),
        "ops": [],
        "claimed_obligations": {
            "requires_c_do": bool(base_ontology.get("supports_macro_do", False)),
            "requires_c_mdl": True,
            "requires_c_inv": True,
            "requires_c_anti": True,
        },
        "predicted_gains": {
            "delta_mdl_bits": 0,
            "delta_worst_case_success": 0.0,
            "delta_efficiency": 0.0,
        },
    }
    mech_diff = {
        "format": "mechanism_registry_diff_v1_1",
        "schema_version": 1,
        "base_mech_hash": mechanism_hash(base_mech),
        "ops": [],
    }
    manifest = build_manifest(
        base_ontology=base_ontology,
        base_mech=base_mech,
        suite_id_dev=suite_id_dev,
        suite_id_heldout=suite_id_heldout,
        claimed_supports_macro_do=bool(base_ontology.get("supports_macro_do", False)),
        ontology_patch=patch,
        mechanism_diff=mech_diff,
        programs_by_path={},
    )
    tar_bytes = build_candidate_tar_bytes(manifest, patch, mech_diff, {})
    return {
        "candidate_id": manifest["candidate_id"],
        "tar_bytes": tar_bytes,
        "op_id": "IDENTITY",
        "local_meta": {"op_id": "IDENTITY", "identity": True},
    }


def _collect_evaluations_for_indices(
    candidates: list[dict[str, Any]],
    cdel_results_dir: Path,
    indices: list[int],
) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    for idx in indices:
        evidence_path = cdel_results_dir / f"candidate_{idx}" / "evidence_report.json"
        if not evidence_path.exists():
            raise RuntimeError(f"missing evidence_report.json for candidate_{idx}")
        parsed = parse_evidence_report(evidence_path)
        parsed["op_id"] = candidates[idx].get("op_id")
        parsed["candidate_index"] = idx
        evaluations.append(parsed)
    return evaluations


def _apply_candidate_quota(
    candidates: list[dict[str, Any]],
    *,
    max_candidates: int,
    min_by_op: dict[str, int],
    max_by_op: dict[str, int],
) -> list[dict[str, Any]]:
    if max_candidates <= 0:
        return []
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    counts: dict[str, int] = {}

    def _add(candidate: dict[str, Any]) -> None:
        cid = candidate.get("candidate_id")
        if not cid or cid in selected_ids:
            return
        if len(selected) >= max_candidates:
            return
        op_id = candidate.get("op_id", "")
        if op_id in max_by_op and counts.get(op_id, 0) >= max_by_op[op_id]:
            return
        selected.append(candidate)
        selected_ids.add(cid)
        counts[op_id] = counts.get(op_id, 0) + 1

    for op_id, min_count in min_by_op.items():
        if min_count <= 0:
            continue
        for cand in candidates:
            if cand.get("op_id") != op_id:
                continue
            if counts.get(op_id, 0) >= min_count:
                break
            _add(cand)

    for cand in candidates:
        if len(selected) >= max_candidates:
            break
        _add(cand)

    return selected


def _screen_rank_key(item: dict[str, Any]) -> tuple:
    mdl_improve = item.get("heldout_mdl_improvement_bits")
    if mdl_improve is None:
        mdl_improve = item.get("mdl_delta", 0.0)
    wcs = item.get("heldout_worst_case_success_eval", item.get("heldout_worst_case_success", 0.0))
    wce = item.get("heldout_worst_case_efficiency_eval", item.get("heldout_worst_case_efficiency", 0.0))
    return (
        -float(wcs),
        -float(mdl_improve),
        -float(wce),
        str(item.get("candidate_id")),
    )


def _best_candidate_for_breakdown(evaluations: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not evaluations:
        return None
    return sorted(evaluations, key=_screen_rank_key)[0]


def _is_hex64(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _load_retest_entry(state: dict[str, Any], state_dir: Path) -> dict[str, Any] | None:
    if not state.get("retest_pending"):
        return None
    retest_id = state.get("retest_candidate_id")
    if not isinstance(retest_id, str) or not _is_hex64(retest_id):
        raise RuntimeError("retest_pending set but retest_candidate_id invalid")
    retest_path = Path(state_dir) / "retest_candidate.tar"
    if not retest_path.exists():
        raise RuntimeError("retest_pending set but retest_candidate.tar missing")
    tar_bytes = retest_path.read_bytes()
    op_id = state.get("retest_candidate_op_id", "none")
    return {
        "candidate_id": retest_id,
        "tar_bytes": tar_bytes,
        "op_id": op_id,
        "local_meta": {"op_id": op_id, "retest": True},
    }


def _retest_base_hash_from_tar(tar_bytes: bytes) -> str:
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tf:
        manifest = tf.extractfile("manifest.json")
        if manifest is None:
            raise ValueError("retest tar missing manifest.json")
        data = json.loads(manifest.read().decode("utf-8"))
    return str(data.get("base_ontology_hash") or "")


def _run_cdel_job(job: dict[str, Any]) -> int:
    run_cdel_verify(
        cdel_bin=job["cdel_bin"],
        candidate_tar=job["candidate_tar"],
        base_ontology=job["base_ontology"],
        base_mech=job["base_mech"],
        suitepack_dev=job["suitepack_dev"],
        suitepack_heldout=job["suitepack_heldout"],
        out_dir=job["out_dir"],
        eval_plan=job.get("eval_plan"),
        screen_dev_episodes=job.get("screen_dev_episodes"),
        screen_heldout_episodes=job.get("screen_heldout_episodes"),
        no_logs_on_fail=job.get("no_logs_on_fail"),
        progress_interval=job.get("progress_interval"),
        progress_path=job.get("progress_path"),
    )
    progress_path = job.get("progress_path")
    if progress_path and not Path(progress_path).exists():
        raise RuntimeError("progress.json missing after CDEL run")
    return int(job["index"])


def run_epoch(args: argparse.Namespace) -> None:
    if args.max_candidates > 64:
        raise SystemExit("--max_candidates must be <= 64")
    if args.eval_plan == "screen" and args.full_top_k < 1:
        raise SystemExit("--full_top_k must be >= 1 when eval_plan=screen")
    if args.workers < 1 or args.workers > 6:
        raise SystemExit("--workers must be between 1 and 6")

    if os.environ.get("CAOE_TEST_DENY_HELDOUT_OPEN") == "1":
        import builtins

        heldout_path = Path(args.suitepack_heldout).resolve()
        original_open = builtins.open

        def guarded_open(path, *open_args, **open_kwargs):
            if Path(path).resolve() == heldout_path:
                raise RuntimeError("heldout path read")
            return original_open(path, *open_args, **open_kwargs)

        builtins.open = guarded_open

    base_ontology_path = Path(args.base_ontology)
    base_mech_path = Path(args.base_mech)
    suitepack_dev_path = Path(args.suitepack_dev)

    base_ontology = load_json(base_ontology_path)
    base_mech = load_json(base_mech_path)
    suitepack_dev = load_json(suitepack_dev_path)
    dev_nuisance_episodes = _nuisance_k2_episodes(suitepack_dev)
    dev_nuisance_gate_episodes = _augment_nuisance_k2_gate(dev_nuisance_episodes, [11, 22, 33])

    suite_id_dev = extract_suite_id(suitepack_dev)
    suite_id_heldout = args.heldout_suite_id
    if not suite_id_heldout:
        raise SystemExit("--heldout_suite_id is required")

    state = load_state(args.state_dir)
    epoch_num = int(state.get("current_epoch", 0)) + 1
    retest_entry: dict[str, Any] | None = _load_retest_entry(state, Path(args.state_dir))
    retest_skip_reason: str | None = None
    if retest_entry is not None:
        try:
            retest_base_hash = _retest_base_hash_from_tar(retest_entry["tar_bytes"])
        except Exception as exc:  # pragma: no cover - fail closed on malformed retest tar
            raise RuntimeError(f"retest_candidate.tar invalid: {exc}") from exc
        current_base_hash = ontology_hash(base_ontology)
        if retest_base_hash != current_base_hash:
            retest_skip_reason = "RETEST_BASE_HASH_MISMATCH"
            retest_entry = None
            state["retest_pending"] = False
            state["retest_candidate_id"] = ""
            state["retest_candidate_op_id"] = ""

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    anomaly_buffer, _identity_id = run_identity_and_mine(
        base_ontology=base_ontology,
        base_mech=base_mech,
        base_ontology_path=base_ontology_path,
        base_mech_path=base_mech_path,
        suite_id_dev=suite_id_dev,
        suite_id_heldout=suite_id_heldout,
        suitepack_dev_path=suitepack_dev_path,
        suitepack_heldout_path=args.suitepack_heldout,
        cdel_bin=args.cdel_bin,
        epoch_id=args.epoch_id,
        out_dir=out_dir,
        eval_plan=args.eval_plan,
        screen_dev_episodes=args.screen_dev_episodes,
        screen_heldout_episodes=args.screen_heldout_episodes,
        no_logs_on_fail=(args.eval_plan == "screen"),
        progress_interval=args.progress_interval,
        progress_path=out_dir / "progress_identity.json",
    )
    sequence_oracle = _load_optional_json(args.dev_oracle_sequence)
    memoryless_oracle = _load_optional_json(args.dev_oracle_memoryless)
    depth2_oracle = _load_optional_json(args.dev_oracle_depth2)
    dev_classification = classify_nuisance_rate_scale(
        anomaly_buffer=anomaly_buffer,
        sequence_oracle=sequence_oracle,
        memoryless_oracle=memoryless_oracle,
        depth2_oracle=depth2_oracle,
    )
    anomaly_buffer["dev_classification"] = dev_classification
    diag_dir = out_dir / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    diag_path = diag_dir / "nuisance_rate_scale_classification.json"
    _write_text_json(diag_path, dev_classification)
    _write_text_json(out_dir / "anomaly_buffer.json", anomaly_buffer)

    min_by_op, max_by_op, budget_by_family = _candidate_budgets(
        anomaly_buffer=anomaly_buffer,
        dev_classification=dev_classification,
    )

    proposals, proposal_stats = propose_candidates_with_stats(
        anomaly_buffer=anomaly_buffer,
        base_ontology=base_ontology,
        base_mech=base_mech,
        proposer_state=state,
        epoch_num=epoch_num,
    )
    op_ranks = operator_rankings(state)
    candidates = synthesize_candidates(
        proposals=proposals,
        base_ontology=base_ontology,
        base_mech=base_mech,
        suite_id_dev=suite_id_dev,
        suite_id_heldout=suite_id_heldout,
        claimed_supports_macro_do=bool(base_ontology.get("supports_macro_do", False)),
        operator_ranks=op_ranks,
    )
    proposal_generation_summary = {
        "format": "caoe_proposal_generation_summary_v1_1",
        "schema_version": 1,
        "total_proposals_considered": int(sum((proposal_stats.get("counts_by_operator") or {}).values())),
        "total_candidates_produced": int(len(candidates)),
        "counts_by_operator": proposal_stats.get("counts_by_operator") or {},
        "skip_reason_counts": proposal_stats.get("skip_reason_counts") or {},
        "skipped_by_operator_counts": proposal_stats.get("skipped_by_operator_counts") or {},
        "candidate_budget_by_family": budget_by_family,
        "candidate_budget_by_operator": {"min_by_operator": min_by_op, "max_by_operator": max_by_op},
    }
    if retest_skip_reason:
        skip_counts = proposal_generation_summary.get("skip_reason_counts") or {}
        skip_counts[retest_skip_reason] = int(skip_counts.get(retest_skip_reason, 0)) + 1
        proposal_generation_summary["skip_reason_counts"] = skip_counts
    identity_candidate = _build_identity_candidate(
        base_ontology=base_ontology,
        base_mech=base_mech,
        suite_id_dev=suite_id_dev,
        suite_id_heldout=suite_id_heldout,
    )
    ids_seen = {cand.get("candidate_id") for cand in candidates if cand.get("candidate_id")}
    reserved_slots = 0
    if retest_entry is not None:
        reserved_slots += 1
    if identity_candidate.get("candidate_id") not in ids_seen:
        reserved_slots += 1
    quota_max = max(int(args.max_candidates) - reserved_slots, 0)
    candidates = _apply_candidate_quota(
        candidates,
        max_candidates=quota_max,
        min_by_op=min_by_op,
        max_by_op=max_by_op,
    )
    ids_seen = {cand.get("candidate_id") for cand in candidates if cand.get("candidate_id")}
    merged: list[dict[str, Any]] = []
    if retest_entry is not None:
        merged.append(retest_entry)
    if identity_candidate.get("candidate_id") not in ids_seen:
        merged.append(identity_candidate)
    merged.extend(
        [
            cand
            for cand in candidates
            if cand.get("candidate_id") not in {item.get("candidate_id") for item in merged}
        ]
    )
    candidates = merged
    candidates = candidates[: args.max_candidates]
    _write_text_json(out_dir / "proposal_generation_summary.json", proposal_generation_summary)

    candidates_dir = out_dir / "candidates"
    cdel_results_screen = out_dir / "cdel_results_screen"
    cdel_results_full = out_dir / "cdel_results_full"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    cdel_results_screen.mkdir(parents=True, exist_ok=True)
    cdel_results_full.mkdir(parents=True, exist_ok=True)

    for idx, cand in enumerate(candidates):
        tar_path = candidates_dir / f"candidate_{idx}.tar"
        tar_path.write_bytes(cand["tar_bytes"])
        _write_text_json(candidates_dir / f"candidate_{idx}_local_meta.json", cand["local_meta"])

    diff_summary = []
    for idx, cand in enumerate(candidates):
        ontology_ops = cand.get("ontology_patch", {}).get("ops") or []
        mech_ops = cand.get("mech_diff", {}).get("ops") or []
        diff_summary.append(
            {
                "candidate_index": idx,
                "candidate_id": cand.get("candidate_id", ""),
                "op_id": cand.get("op_id", ""),
                "operator_rank": cand.get("operator_rank", 0),
                "predicted_priority": cand.get("predicted_priority", 0),
                "predicted_gains": (cand.get("local_meta") or {}).get("predicted_gains", {}),
                "ontology_ops_summary": _summarize_ontology_ops(ontology_ops),
                "mech_ops_summary": _summarize_mech_ops(mech_ops),
            }
        )
    _write_text_json(
        out_dir / "candidate_diff_summary.json",
        {"format": "caoe_candidate_diff_summary_v1_1", "schema_version": 1, "entries": diff_summary},
    )

    screen_jobs: list[dict[str, Any]] = []
    screen_out_dir = cdel_results_screen if args.eval_plan == "screen" else cdel_results_full
    progress_suffix = "screen" if args.eval_plan == "screen" else "full"
    for idx in range(len(candidates)):
        tar_path = candidates_dir / f"candidate_{idx}.tar"
        candidate_out_dir = screen_out_dir / f"candidate_{idx}"
        screen_jobs.append(
            {
                "index": idx,
                "cdel_bin": args.cdel_bin,
                "candidate_tar": tar_path,
                "base_ontology": base_ontology_path,
                "base_mech": base_mech_path,
                "suitepack_dev": suitepack_dev_path,
                "suitepack_heldout": args.suitepack_heldout,
                "out_dir": candidate_out_dir,
                "eval_plan": "screen" if args.eval_plan == "screen" else "full",
                "screen_dev_episodes": args.screen_dev_episodes,
                "screen_heldout_episodes": args.screen_heldout_episodes,
                "no_logs_on_fail": args.eval_plan == "screen",
                "progress_interval": args.progress_interval,
                "progress_path": out_dir / f"progress_candidate_{idx}_{progress_suffix}.json",
            }
        )

    if args.eval_plan == "screen":
        if args.workers <= 1:
            done_indices = [int(_run_cdel_job(job)) for job in screen_jobs]
        else:
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                futures = [pool.submit(_run_cdel_job, job) for job in screen_jobs]
                done_indices = [future.result() for future in futures]
        done_indices.sort()
    else:
        for job in screen_jobs:
            _run_cdel_job(job)

    evaluations_screen = _collect_evaluations(candidates, screen_out_dir)
    ranked = sorted(evaluations_screen, key=_screen_rank_key)
    selected_indices = [int(item.get("candidate_index")) for item in ranked[: args.full_top_k]] if ranked else []

    evaluations_full: list[dict[str, Any]] = []
    if args.eval_plan == "screen":
        for idx in selected_indices:
            tar_path = candidates_dir / f"candidate_{idx}.tar"
            candidate_out_dir = cdel_results_full / f"candidate_{idx}"
            run_cdel_verify(
                cdel_bin=args.cdel_bin,
                candidate_tar=tar_path,
                base_ontology=base_ontology_path,
                base_mech=base_mech_path,
                suitepack_dev=suitepack_dev_path,
                suitepack_heldout=args.suitepack_heldout,
                out_dir=candidate_out_dir,
                eval_plan="full",
                progress_interval=args.progress_interval,
                progress_path=out_dir / f"progress_candidate_{idx}_full.json",
            )
            progress_path = out_dir / f"progress_candidate_{idx}_full.json"
            if not progress_path.exists():
                raise RuntimeError("progress.json missing after full CDEL run")
        evaluations_full = _collect_evaluations_for_indices(candidates, cdel_results_full, selected_indices)
    else:
        evaluations_full = evaluations_screen

    # Write selection_debug.json for traceability.
    screen_ranked: list[dict[str, Any]] = []
    screen_results_dir = cdel_results_screen if args.eval_plan == "screen" else cdel_results_full
    for cand_dir in sorted(screen_results_dir.glob("candidate_*")):
        evidence_path = cand_dir / "evidence_report.json"
        if not evidence_path.exists():
            raise RuntimeError("missing screen evidence_report.json")
        report = load_json(evidence_path)
        cand_metrics = report.get("candidate_metrics", {})
        base_metrics = report.get("base_metrics", {})
        cand_inv = cand_metrics.get("c_inv", {})
        base_mdl = base_metrics.get("c_mdl", {})
        cand_mdl = cand_metrics.get("c_mdl", {})
        diagnostics = cand_metrics.get("diagnostics", {})
        if "phi_fingerprint" not in diagnostics:
            raise RuntimeError("missing phi_fingerprint in screen diagnostics")
        wcs = float(cand_inv.get("heldout_worst_case_success", 0.0))
        wce = float(cand_inv.get("heldout_worst_case_efficiency", 0.0))
        wcs_eval = float(cand_inv.get("heldout_worst_case_success_eval", wcs))
        wce_eval = float(cand_inv.get("heldout_worst_case_efficiency_eval", wce))
        base_dev_bits = float(base_mdl.get("dev_tml_bits", 0.0))
        cand_dev_bits = float(cand_mdl.get("dev_tml_bits", 0.0))
        screen_ranked.append(
            {
                "candidate_id": report.get("candidate_id", ""),
                "heldout_worst_case_success": wcs,
                "heldout_worst_case_success_eval": wcs_eval,
                "heldout_worst_case_efficiency": wce,
                "heldout_worst_case_efficiency_eval": wce_eval,
                "heldout_avg_success": _avg_success(cand_inv.get("per_regime_success", {})),
                "mdl_delta": float(base_mdl.get("heldout_tml_bits", 0.0))
                - float(cand_mdl.get("heldout_tml_bits", 0.0)),
                "heldout_mdl_improvement_bits": float(base_mdl.get("heldout_tml_bits", 0.0))
                - float(cand_mdl.get("heldout_tml_bits", 0.0)),
                "dev_mdl_delta": base_dev_bits - cand_dev_bits,
                "phi_fingerprint": diagnostics.get("phi_fingerprint", ""),
            }
        )
    screen_ranked.sort(key=_screen_rank_key)

    full_evaluated: list[str] = []
    full_results: list[dict[str, Any]] = []
    if cdel_results_full.exists():
        for cand_dir in sorted(cdel_results_full.glob("candidate_*")):
            evidence_path = cand_dir / "evidence_report.json"
            if not evidence_path.exists():
                raise RuntimeError("missing full evidence_report.json")
            report = load_json(evidence_path)
            cand_metrics = report.get("candidate_metrics", {})
            base_metrics = report.get("base_metrics", {})
            cand_inv = cand_metrics.get("c_inv", {})
            base_mdl = base_metrics.get("c_mdl", {})
            cand_mdl = cand_metrics.get("c_mdl", {})
            diagnostics = cand_metrics.get("diagnostics", {})
            if "phi_fingerprint" not in diagnostics or "policy_fingerprint" not in diagnostics:
                raise RuntimeError("missing diagnostics in full evidence")
            candidate_id = report.get("candidate_id", "")
            wcs = float(cand_inv.get("heldout_worst_case_success", 0.0))
            wce = float(cand_inv.get("heldout_worst_case_efficiency", 0.0))
            wcs_eval = float(cand_inv.get("heldout_worst_case_success_eval", wcs))
            wce_eval = float(cand_inv.get("heldout_worst_case_efficiency_eval", wce))
            base_dev_bits = float(base_mdl.get("dev_tml_bits", 0.0))
            cand_dev_bits = float(cand_mdl.get("dev_tml_bits", 0.0))
            full_evaluated.append(candidate_id)
            full_results.append(
                {
                    "candidate_id": candidate_id,
                    "heldout_worst_case_success": wcs,
                    "heldout_worst_case_success_eval": wcs_eval,
                    "heldout_worst_case_efficiency": wce,
                    "heldout_worst_case_efficiency_eval": wce_eval,
                    "mdl_delta": float(base_mdl.get("heldout_tml_bits", 0.0))
                    - float(cand_mdl.get("heldout_tml_bits", 0.0)),
                    "dev_mdl_delta": base_dev_bits - cand_dev_bits,
                    "decision": report.get("decision", ""),
                    "failed_contract": report.get("failed_contract", ""),
                    "phi_fingerprint": diagnostics.get("phi_fingerprint", ""),
                    "policy_fingerprint": diagnostics.get("policy_fingerprint", ""),
                }
            )

    selection_debug = {
        "format": "caoe_selection_debug_v1_1",
        "schema_version": 1,
        "screen_ranked": screen_ranked,
        "full_evaluated": full_evaluated,
        "full_results": full_results,
    }
    _write_text_json(out_dir / "selection_debug.json", selection_debug)

    # Floor diagnostics: prefer full evaluations, fall back to screen evidence.
    floor_entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for cand_dir in sorted(cdel_results_full.glob("candidate_*")):
        evidence_path = cand_dir / "evidence_report.json"
        if not evidence_path.exists():
            continue
        report = load_json(evidence_path)
        candidate_id = report.get("candidate_id", "")
        entry = _floor_diagnostic_from_report(report)
        entry["candidate_id"] = candidate_id
        entry["source"] = "full"
        floor_entries.append(entry)
        if candidate_id:
            seen_ids.add(candidate_id)
    screen_results_dir = cdel_results_screen if args.eval_plan == "screen" else cdel_results_full
    for cand_dir in sorted(screen_results_dir.glob("candidate_*")):
        evidence_path = cand_dir / "evidence_report.json"
        if not evidence_path.exists():
            continue
        report = load_json(evidence_path)
        candidate_id = report.get("candidate_id", "")
        if candidate_id and candidate_id in seen_ids:
            continue
        entry = _floor_diagnostic_from_report(report)
        entry["candidate_id"] = candidate_id
        entry["source"] = "screen" if args.eval_plan == "screen" else "full"
        floor_entries.append(entry)
    _write_text_json(
        out_dir / "floor_diagnostic.json",
        {"format": "caoe_floor_diagnostic_v1_1", "schema_version": 1, "entries": floor_entries},
    )

    # Collect evidence reports for downstream audit artifacts.
    evidence_by_id: dict[str, dict[str, Any]] = {}
    evidence_dir_by_id: dict[str, Path] = {}
    receipt_src_by_id: dict[str, Path] = {}
    full_evidence_ids: set[str] = set()
    screen_evidence_ids: set[str] = set()

    def _ingest_results(results_dir: Path, *, allow_overwrite: bool, record_set: set[str]) -> None:
        for cand_dir in sorted(results_dir.glob("candidate_*")):
            evidence_path = cand_dir / "evidence_report.json"
            if not evidence_path.exists():
                continue
            report = load_json(evidence_path)
            candidate_id = str(report.get("candidate_id") or "")
            if not candidate_id:
                continue
            record_set.add(candidate_id)
            if candidate_id in evidence_by_id and not allow_overwrite:
                continue
            evidence_by_id[candidate_id] = report
            evidence_dir_by_id[candidate_id] = cand_dir
            receipt_path = cand_dir / "receipt.json"
            if receipt_path.exists():
                receipt_src_by_id[candidate_id] = receipt_path

    if cdel_results_full.exists():
        _ingest_results(cdel_results_full, allow_overwrite=True, record_set=full_evidence_ids)
    if args.eval_plan == "screen" and cdel_results_screen.exists():
        _ingest_results(cdel_results_screen, allow_overwrite=False, record_set=screen_evidence_ids)

    # Copy receipts into deterministic epoch-local paths with manifests.
    receipts_dir = out_dir / "receipts"
    receipt_relpath_by_id: dict[str, str] = {}
    receipt_sha_by_id: dict[str, str] = {}
    for candidate_id in sorted(receipt_src_by_id.keys()):
        src_path = receipt_src_by_id[candidate_id]
        dest_dir = receipts_dir / candidate_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / "receipt.json"
        shutil.copyfile(src_path, dest_path)
        receipt_sha = _sha256_hex_file(dest_path)
        receipt_relpath_by_id[candidate_id] = dest_path.relative_to(out_dir).as_posix()
        receipt_sha_by_id[candidate_id] = receipt_sha
        report = evidence_by_id.get(candidate_id, {})
        failed_contract = str(report.get("failed_contract") or "")
        format_error = bool(report.get("format_error"))
        if format_error:
            reason_code = "FORMAT_ERROR"
        elif failed_contract and failed_contract != "NONE":
            reason_code = f"FAIL_{failed_contract}"
        elif report.get("decision") == "PASS":
            reason_code = "PASS"
        else:
            reason_code = "UNKNOWN"
        receipt_manifest = {
            "format": "caoe_receipt_manifest_v1_1",
            "schema_version": 1,
            "candidate_id": candidate_id,
            "receipt_sha256": receipt_sha,
            "verdict": str(report.get("decision") or "FAIL"),
            "failed_contract": failed_contract or "NONE",
            "reason_code": reason_code,
        }
        _write_text_json(dest_dir / "receipt_manifest.json", receipt_manifest)

    # Attach proposal metadata to phi debug artifacts.
    for cand in candidates:
        candidate_id = str(cand.get("candidate_id") or "")
        if not candidate_id:
            continue
        op_id = str(cand.get("op_id") or "")
        phi_prog, _ = _candidate_phi_program(cand, base_ontology)
        phi_input_name = _phi_input_name_used(phi_prog)
        evidence_dir = evidence_dir_by_id.get(candidate_id)
        _augment_phi_debug_files(candidate_id, _operator_name(op_id), op_id, phi_input_name, evidence_dir)

    dev_gate_required = bool(dev_nuisance_gate_episodes) and _nuisance_family_present(anomaly_buffer)
    dev_gate_by_id: dict[str, Any] = {}
    if dev_gate_required:
        for cand in candidates:
            candidate_id = str(cand.get("candidate_id") or "")
            if not candidate_id:
                continue
            report = evidence_by_id.get(candidate_id)
            evidence_dir = evidence_dir_by_id.get(candidate_id)
            if report is None or evidence_dir is None:
                dev_gate_by_id[candidate_id] = {
                    "passed": False,
                    "success_count": 0,
                    "total_required": len(dev_nuisance_gate_episodes),
                    "episodes": [],
                    "reason": "missing_evidence",
                }
                continue
            cand_ontology = _candidate_ontology_for_gate(cand, base_ontology)
            if cand_ontology is None:
                dev_gate_by_id[candidate_id] = {
                    "passed": False,
                    "success_count": 0,
                    "total_required": len(dev_nuisance_gate_episodes),
                    "episodes": [],
                    "reason": "ontology_patch_failed",
                }
                continue
            dev_logs = _load_intervention_logs(report, evidence_dir, suite_track="dev", variant="candidate")
            success_map = compute_episode_successes(
                ontology=cand_ontology,
                suitepack=suitepack_dev,
                logs=dev_logs,
            )
            episode_rows: list[dict[str, Any]] = []
            success_count = 0
            for ep in dev_nuisance_gate_episodes:
                ep_id = str(ep.get("episode_id") or "")
                source_id = str(ep.get("source_episode_id") or "")
                if ep_id in success_map:
                    success = bool(success_map.get(ep_id))
                elif source_id and source_id in success_map:
                    success = bool(success_map.get(source_id))
                else:
                    success = False
                if success:
                    success_count += 1
                episode_rows.append(
                    {
                        "episode_id": ep_id,
                        "regime_id": str(ep.get("regime_id") or ""),
                        "seed": int(ep.get("seed", 0)) if ep.get("seed") is not None else 0,
                        "source_episode_id": str(ep.get("source_episode_id") or ""),
                        "success": int(success),
                    }
                )
            dev_gate_by_id[candidate_id] = {
                "passed": success_count >= 3,
                "success_count": success_count,
                "total_required": len(dev_nuisance_gate_episodes),
                "episodes": episode_rows,
                "reason": "ok",
            }

    # Build per-regime base metrics and best candidate metrics from evidence.
    per_regime_base: dict[str, Any] = {}
    per_regime_best: dict[str, Any] = {}
    episode_counts: dict[str, int] = {}
    sample_report = None
    sample_candidate_id = ""
    if full_evidence_ids:
        sample_candidate_id = sorted(full_evidence_ids)[0]
        sample_report = evidence_by_id.get(sample_candidate_id)
    if sample_report is None and evidence_by_id:
        sample_candidate_id = next(iter(evidence_by_id.keys()))
        sample_report = evidence_by_id.get(sample_candidate_id)
    base_success_map: dict[str, float] = {}
    if sample_report:
        base_inv = (sample_report.get("base_metrics") or {}).get("c_inv") or {}
        base_success = base_inv.get("per_regime_success") or {}
        base_eff = base_inv.get("per_regime_efficiency") or {}
        # Count episodes using certified intervention logs.
        sample_dir = evidence_dir_by_id.get(sample_candidate_id, out_dir)
        logs = (sample_report.get("artifacts") or {}).get("intervention_logs") or []
        for entry in logs:
            if entry.get("suite_track") != "heldout" or entry.get("variant") != "base":
                continue
            rel = entry.get("relative_path")
            if not rel:
                continue
            log_path = sample_dir / str(rel)
            if not log_path.exists():
                continue
            log_data = load_json(log_path)
            rid = str(log_data.get("regime_id") or "")
            if rid:
                episode_counts[rid] = episode_counts.get(rid, 0) + 1
        for rid in sorted(base_success.keys()):
            per_regime_base[rid] = {
                "success_rate": float(base_success.get(rid, 0.0)),
                "efficiency": float(base_eff.get(rid, 0.0)),
                "episode_count": int(episode_counts.get(rid, 0)),
            }
            base_success_map[rid] = float(base_success.get(rid, 0.0))

    success_matrix: dict[str, dict[str, float]] = {}
    for candidate_id, report in evidence_by_id.items():
        cand_inv = (report.get("candidate_metrics") or {}).get("c_inv") or {}
        cand_success = cand_inv.get("per_regime_success") or {}
        cand_eff = cand_inv.get("per_regime_efficiency") or {}
        success_matrix[candidate_id] = {rid: float(val) for rid, val in cand_success.items()}
        for rid, success_val in cand_success.items():
            success = float(success_val)
            eff = float(cand_eff.get(rid, 0.0))
            cur = per_regime_best.get(rid)
            if cur is None or success > float(cur.get("success_rate", 0.0)) or (
                success == float(cur.get("success_rate", 0.0)) and eff > float(cur.get("efficiency", 0.0))
            ):
                per_regime_best[rid] = {
                    "candidate_id": candidate_id,
                    "success_rate": success,
                    "efficiency": eff,
                }

    _write_text_json(
        out_dir / "per_regime_base_metrics.json",
        {"format": "caoe_per_regime_base_metrics_v1_1", "schema_version": 1, "regimes": per_regime_base},
    )
    _write_text_json(
        out_dir / "per_regime_candidate_best.json",
        {"format": "caoe_per_regime_candidate_best_v1_1", "schema_version": 1, "regimes": per_regime_best},
    )
    _write_text_json(
        out_dir / "success_matrix.json",
        {
            "format": "caoe_success_matrix_v1_1",
            "schema_version": 1,
            "base": {rid: float(val) for rid, val in base_success_map.items()},
            "candidates": success_matrix,
        },
    )
    _update_lifecycle_state(Path(args.state_dir), str(args.epoch_id), base_success_map)

    # Emit a failure example for one zero-success regime (if available).
    zero_regimes = [rid for rid, entry in per_regime_base.items() if float(entry.get("success_rate", 0.0)) == 0.0]
    zero_regime_count = sum(
        1 for entry in per_regime_best.values() if float(entry.get("success_rate", 0.0)) == 0.0
    )
    if zero_regimes and sample_report:
        target_regime = sorted(zero_regimes)[0]
        sample_dir = evidence_dir_by_id.get(sample_candidate_id, out_dir)
        logs = (sample_report.get("artifacts") or {}).get("intervention_logs") or []
        failure_log_path: Path | None = None
        for entry in logs:
            if entry.get("suite_track") != "heldout" or entry.get("variant") != "base":
                continue
            rel = entry.get("relative_path")
            if not rel:
                continue
            log_path = sample_dir / str(rel)
            if not log_path.exists():
                continue
            log_data = load_json(log_path)
            if str(log_data.get("regime_id") or "") == target_regime:
                failure_log_path = log_path
                break
        if failure_log_path is not None:
            failure_dir = out_dir / "regime_failure_examples" / target_regime
            failure_dir.mkdir(parents=True, exist_ok=True)
            log_data = load_json(failure_log_path)
            _write_text_json(failure_dir / "agent_outputs.json", log_data)
            _write_text_json(
                failure_dir / "episode_spec.json",
                {
                    "format": "caoe_episode_spec_stub_v1_1",
                    "schema_version": 1,
                    "episode_id": log_data.get("episode_id"),
                    "regime_id": log_data.get("regime_id"),
                    "suite_id": log_data.get("suite_id"),
                    "note": "Episode goal/initial state unavailable from certified logs; use suitepack if permitted.",
                },
            )
            _write_text_json(
                failure_dir / "scorer_inputs.json",
                {
                    "format": "caoe_scorer_inputs_v1_1",
                    "schema_version": 1,
                    "episode_id": log_data.get("episode_id"),
                    "regime_id": log_data.get("regime_id"),
                    "records": log_data.get("records", []),
                },
            )
            reproduce_script = f"""import json\nimport sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path('{Path.cwd() / 'CDEL-v2'}').resolve()))\nfrom extensions.caoe_v1.eval.suitepack_reader_v1 import load_suitepack, SuitepackV1\nfrom extensions.caoe_v1.eval.ccai_x_core_v1 import evaluate_suite\nfrom extensions.caoe_v1.eval.run_eval_v1 import load_json\n\nbase_ontology = load_json('{base_ontology_path}')\nbase_mech = load_json('{base_mech_path}')\nsuitepack = load_suitepack('{args.suitepack_heldout}')\n\ntarget_id = '{log_data.get('episode_id', '')}'\nby_id = {{ep.episode_id: ep for ep in suitepack.episodes}}\nif target_id not in by_id:\n    raise SystemExit('episode_id not found')\nsubset = SuitepackV1(\n    suite_id=suitepack.suite_id,\n    target_env_id=suitepack.target_env_id,\n    episodes=[by_id[target_id]],\n    regimes=suitepack.regimes,\n    shift_families=suitepack.shift_families,\n    suite_token=suitepack.suite_token,\n)\nresults = evaluate_suite(base_ontology, base_mech, subset, episode_ids=[target_id])\nres = results[0]\nprint('success', res.success)\nprint('steps_taken', res.steps_taken)\n\"\"\"\n"""
            (failure_dir / "reproduce_score.py").write_text(reproduce_script, encoding="utf-8")
            (failure_dir / "reproduce_command.txt").write_text(
                "python3 reproduce_score.py\n",
                encoding="utf-8",
            )

    # Build candidate decisions with per-contract metrics.
    candidates_by_id = {cand.get("candidate_id"): cand for cand in candidates if cand.get("candidate_id")}
    ordered_ids = [cand.get("candidate_id", "") for cand in candidates if cand.get("candidate_id")]
    candidate_decisions: list[dict[str, Any]] = []
    candidates_evaluated: list[str] = []
    candidates_eligible: list[str] = []
    candidates_rejected: list[dict[str, Any]] = []
    regression_count = 0

    for candidate_id in ordered_ids:
        cand = candidates_by_id.get(candidate_id, {})
        op_id = str(cand.get("op_id") or "")
        phi_prog, replaced_phi = _candidate_phi_program(cand, base_ontology)
        phi_input_name = _phi_input_name_used(phi_prog)
        phi_operator_id = _phi_operator_id_used(op_id, phi_input_name, replaced_phi)
        report = evidence_by_id.get(candidate_id)
        ineligible_reason_codes: list[str] = []
        reason_codes: list[str] = []
        if report is None:
            ineligible_reason_codes.append("NO_EVIDENCE")
            reason_codes.append("NO_EVIDENCE")
        else:
            candidates_evaluated.append(candidate_id)
            if report.get("format_error"):
                ineligible_reason_codes.append("FORMAT_ERROR")
                reason_codes.append("FORMAT_ERROR")
            if args.eval_plan == "screen" and candidate_id not in full_evidence_ids:
                ineligible_reason_codes.append("SCREEN_ONLY")
                reason_codes.append("SCREEN_ONLY")
            if dev_gate_required:
                gate_entry = dev_gate_by_id.get(candidate_id, {})
                gate_passed = bool(gate_entry.get("passed")) if isinstance(gate_entry, dict) else False
                if not gate_passed:
                    ineligible_reason_codes.append("FAIL_DEV_NUISANCE_GATE")
                    reason_codes.append("FAIL_DEV_NUISANCE_GATE")
        eligible_for_comparison = not ineligible_reason_codes

        contracts = report.get("contracts") if report else {}
        contracts = contracts or {}
        contract_entries: dict[str, Any] = {}

        cand_metrics = report.get("candidate_metrics", {}) if report else {}
        base_metrics = report.get("base_metrics", {}) if report else {}
        cand_inv = cand_metrics.get("c_inv", {}) if isinstance(cand_metrics, dict) else {}
        base_inv = base_metrics.get("c_inv", {}) if isinstance(base_metrics, dict) else {}
        cand_mdl = cand_metrics.get("c_mdl", {}) if isinstance(cand_metrics, dict) else {}
        base_mdl = base_metrics.get("c_mdl", {}) if isinstance(base_metrics, dict) else {}
        cand_anti = cand_metrics.get("c_anti", {}) if isinstance(cand_metrics, dict) else {}

        c_inv_contract = contracts.get("C-INV") or {}
        c_anti_contract = contracts.get("C-ANTI") or {}
        c_do_contract = contracts.get("C-DO") or {}
        c_mdl_contract = contracts.get("C-MDL") or {}
        c_life_contract = contracts.get("C-LIFE") or {}

        cand_success_map = cand_inv.get("per_regime_success") or {}
        base_success_map_cinv = base_inv.get("per_regime_success") or {}
        cand_avg = _avg_success(cand_success_map)
        cand_min = _min_success(cand_success_map)
        base_avg = _avg_success(base_success_map_cinv)
        base_min = _min_success(base_success_map_cinv)
        contract_entries["C-INV"] = {
            "result": _contract_result(c_inv_contract),
            "metrics": {
                "candidate_avg_success": cand_avg,
                "candidate_worst_case_success": cand_min,
                "candidate_worst_case_success_eval": cand_min,
                "candidate_worst_case_efficiency": cand_inv.get("heldout_worst_case_efficiency"),
                "base_avg_success": base_avg,
                "base_worst_case_success": base_min,
                "base_worst_case_success_eval": base_min,
                "candidate_per_family": cand_inv.get("per_family") or {},
                "base_per_family": base_inv.get("per_family") or {},
            },
        }
        contract_entries["C-ANTI"] = {
            "result": _contract_result(c_anti_contract),
            "metrics": {
                "leakage_sensitivity": cand_anti.get("leakage_sensitivity"),
                "relabel_sensitivity": cand_anti.get("relabel_sensitivity"),
                "contract_metrics": c_anti_contract.get("metrics") or {},
            },
        }
        contract_entries["C-DO"] = {
            "result": _contract_result(c_do_contract),
            "metrics": c_do_contract.get("metrics") or {},
        }
        contract_entries["C-MDL"] = {
            "result": _contract_result(c_mdl_contract),
            "metrics": {
                "dev_tml_bits_base": base_mdl.get("dev_tml_bits"),
                "dev_tml_bits_candidate": cand_mdl.get("dev_tml_bits"),
                "heldout_tml_bits_base": base_mdl.get("heldout_tml_bits"),
                "heldout_tml_bits_candidate": cand_mdl.get("heldout_tml_bits"),
                "delta_min_bits": cand_mdl.get("delta_min_bits"),
                "pass_reason": cand_mdl.get("pass_reason", ""),
                "failure_reason": cand_mdl.get("failure_reason", ""),
            },
        }
        contract_entries["C-LIFE"] = {
            "result": _contract_result(c_life_contract),
            "metrics": c_life_contract.get("metrics") or {},
        }

        for name, contract in (
            ("C-ANTI", c_anti_contract),
            ("C-DO", c_do_contract),
            ("C-MDL", c_mdl_contract),
            ("C-INV", c_inv_contract),
            ("C-LIFE", c_life_contract),
        ):
            if contract.get("pass") is False:
                reason_codes.append(f"FAIL_{name}")

        if _regression_guard_failure(base_success_map, cand_success_map):
            ineligible_reason_codes.append("FAIL_REGRESSION_GUARD")
            reason_codes.append("FAIL_REGRESSION_GUARD")
            regression_count += 1

        eligible_for_comparison = not ineligible_reason_codes
        if eligible_for_comparison and candidate_id not in candidates_eligible:
            candidates_eligible.append(candidate_id)

        decision = str(report.get("decision") or "FAIL") if report else "FAIL"
        if decision not in {"PASS", "FAIL"}:
            reason_codes.append("NO_DECISION")

        if decision != "PASS":
            candidates_rejected.append({"candidate_id": candidate_id, "reason_codes": sorted(set(reason_codes))})

        fail_primary_reason_code = _primary_reason_code(sorted(set(reason_codes)))
        receipt_relpath = receipt_relpath_by_id.get(candidate_id, "")
        receipt_sha = receipt_sha_by_id.get(candidate_id, "")

        candidate_decisions.append(
            {
                "candidate_id": candidate_id,
                "proposal_type": _operator_name(op_id),
                "operator_id": op_id,
                "phi_operator_id_used": phi_operator_id,
                "phi_input_name_used": phi_input_name,
                "eligibility": {
                    "eligible_for_comparison": bool(eligible_for_comparison),
                    "ineligible_reason_codes": sorted(set(ineligible_reason_codes)),
                },
                "contracts": contract_entries,
                "verdict": decision,
                "reason_codes": sorted(set(reason_codes)),
                "fail_primary_reason_code": fail_primary_reason_code,
                "receipt_relpath": receipt_relpath,
                "receipt_sha256": receipt_sha,
            }
        )

    candidate_decisions_payload = {
        "format": "caoe_candidate_decisions_v1_1",
        "schema_version": 1,
        "entries": candidate_decisions,
    }
    candidate_decisions_path = out_dir / "candidate_decisions.json"
    _write_text_json(candidate_decisions_path, candidate_decisions_payload)
    _write_sha256(out_dir / "candidate_decisions.sha256", _sha256_hex_file(candidate_decisions_path))

    blocked_candidate = None
    if dev_gate_required:
        blocked_candidates = []
        for entry in evaluations_full:
            cand_id = str(entry.get("candidate_id") or "")
            if not cand_id:
                continue
            gate_entry = dev_gate_by_id.get(cand_id, {})
            if not isinstance(gate_entry, dict) or not gate_entry.get("passed"):
                continue
            report = evidence_by_id.get(cand_id)
            if not report or report.get("decision") == "PASS":
                continue
            failed_contract = str(report.get("failed_contract") or "")
            if not failed_contract or failed_contract == "NONE":
                continue
            blocked_candidates.append(entry)
        if blocked_candidates:
            blocked_candidate = sorted(blocked_candidates, key=_screen_rank_key)[0]

    if blocked_candidate is not None:
        cand_id = str(blocked_candidate.get("candidate_id") or "")
        report = evidence_by_id.get(cand_id, {})
        cand_metrics = report.get("candidate_metrics") or {}
        base_metrics = report.get("base_metrics") or {}
        cand_mdl = cand_metrics.get("c_mdl") or {}
        base_mdl = base_metrics.get("c_mdl") or {}
        cand_inv = cand_metrics.get("c_inv") or {}
        gate_entry = dev_gate_by_id.get(cand_id, {})
        blocked_payload = {
            "format": "caoe_blocked_by_contract_v1_1",
            "schema_version": 1,
            "candidate_id": cand_id,
            "failed_contract": str(report.get("failed_contract") or ""),
            "decision": str(report.get("decision") or "FAIL"),
            "base_ontology_hash": str(report.get("base_ontology_hash") or ""),
            "base_mech_hash": str(report.get("base_mech_hash") or ""),
            "candidate_ontology_hash": str(report.get("candidate_ontology_hash") or ""),
            "candidate_mech_hash": str(report.get("candidate_mech_hash") or ""),
            "dev_nuisance_gate": {
                "success_count": int(gate_entry.get("success_count", 0)) if isinstance(gate_entry, dict) else 0,
                "total_required": int(gate_entry.get("total_required", 0)) if isinstance(gate_entry, dict) else 0,
            },
            "metrics": {
                "c_inv": {
                    "heldout_worst_case_success": cand_inv.get("heldout_worst_case_success"),
                    "heldout_worst_case_success_eval": cand_inv.get("heldout_worst_case_success_eval"),
                },
                "c_mdl": {
                    "dev_tml_bits_base": base_mdl.get("dev_tml_bits"),
                    "dev_tml_bits_candidate": cand_mdl.get("dev_tml_bits"),
                    "heldout_tml_bits_base": base_mdl.get("heldout_tml_bits"),
                    "heldout_tml_bits_candidate": cand_mdl.get("heldout_tml_bits"),
                    "delta_min_bits": cand_mdl.get("delta_min_bits"),
                    "pass_reason": cand_mdl.get("pass_reason", ""),
                    "failure_reason": cand_mdl.get("failure_reason", ""),
                },
            },
        }
        blocked_path = out_dir / "diagnostics" / "blocked_by_contract.json"
        _write_text_json(blocked_path, blocked_payload)

    evaluations_for_selection = evaluations_full
    if dev_gate_required:
        passed_ids = {
            cand_id for cand_id, entry in dev_gate_by_id.items() if isinstance(entry, dict) and entry.get("passed")
        }
        evaluations_for_selection = [
            entry for entry in evaluations_full if str(entry.get("candidate_id") or "") in passed_ids
        ]
    selection_base = select_candidate(evaluations_for_selection)
    selection = {
        "selected_candidate_id": selection_base.get("selected_candidate_id"),
        "candidates_evaluated": candidates_evaluated,
        "candidates_eligible": candidates_eligible,
        "candidates_rejected": candidates_rejected,
        "candidates_compared": candidates_eligible,
    }
    _write_text_json(out_dir / "selection.json", selection)

    if selection.get("selected_candidate_id") == "none":
        best = _best_candidate_for_breakdown(evaluations_full)
        if best:
            mdl_breakdown = {
                "format": "caoe_mdl_breakdown_v1_1",
                "schema_version": 1,
                "base": {
                    "dev": best.get("base_mdl_breakdown_dev"),
                    "heldout": best.get("base_mdl_breakdown_heldout"),
                },
                "candidate": {
                    "candidate_id": best.get("candidate_id"),
                    "dev": best.get("cand_mdl_breakdown_dev"),
                    "heldout": best.get("cand_mdl_breakdown_heldout"),
                },
            }
            _write_text_json(out_dir / "mdl_breakdown.json", mdl_breakdown)

    updated_state = update_state(
        state=state,
        evaluations=evaluations_full,
        selection=selection,
        epoch_num=epoch_num,
        anomaly_buffer=anomaly_buffer,
    )
    pass_ids = sorted(
        [
            str(item.get("candidate_id"))
            for item in evaluations_full
            if item.get("decision") == "PASS" and item.get("candidate_id")
        ]
    )
    chosen_id = None
    current_retest_id = state.get("retest_candidate_id")
    if state.get("retest_pending") and isinstance(current_retest_id, str) and current_retest_id in pass_ids:
        chosen_id = current_retest_id
    elif pass_ids:
        chosen_id = pass_ids[0]
        if chosen_id:
            by_id = {cand.get("candidate_id"): cand for cand in candidates if cand.get("candidate_id")}
            chosen = by_id.get(chosen_id)
            if chosen is not None:
                retest_path = Path(args.state_dir) / "retest_candidate.tar"
                retest_path.parent.mkdir(parents=True, exist_ok=True)
                retest_path.write_bytes(chosen["tar_bytes"])
            updated_state["retest_candidate_id"] = chosen_id
            updated_state["retest_candidate_op_id"] = chosen.get("op_id", "none")
            updated_state["retest_pending"] = True
    else:
        if updated_state.get("retest_pending"):
            updated_state["retest_candidate_id"] = "none"
            updated_state["retest_candidate_op_id"] = "none"
        updated_state["retest_pending"] = False
    save_state(args.state_dir, updated_state)

    flags = compute_flags(updated_state)
    degenerate_reason_counts: dict[str, int] = {}
    for entry in candidate_decisions:
        for code in entry.get("reason_codes", []):
            if code.startswith("FAIL_C_ANTI"):
                degenerate_reason_counts[code] = degenerate_reason_counts.get(code, 0) + 1
    selected_candidate_id = str(selection.get("selected_candidate_id") or "none")
    dev_gate_selected: dict[str, Any] | None = None
    if dev_gate_required and selected_candidate_id != "none":
        gate_entry = dev_gate_by_id.get(selected_candidate_id)
        if isinstance(gate_entry, dict):
            dev_gate_selected = {
                "candidate_id": selected_candidate_id,
                "success_count": int(gate_entry.get("success_count", 0)),
                "total_required": int(gate_entry.get("total_required", 0)),
                "passed": bool(gate_entry.get("passed")),
            }

    heldout_nuisance_check = {
        "candidate_id": selected_candidate_id,
        "episodes": [],
        "worst_case_success": None,
        "success_source": "per_regime_success",
    }
    if selected_candidate_id != "none":
        report = evidence_by_id.get(selected_candidate_id)
        evidence_dir = evidence_dir_by_id.get(selected_candidate_id)
        if report is not None and evidence_dir is not None:
            cand_inv = (report.get("candidate_metrics") or {}).get("c_inv") or {}
            per_regime_success = cand_inv.get("per_regime_success") or {}
            heldout_logs = _load_intervention_logs(
                report,
                evidence_dir,
                suite_track="heldout",
                variant="candidate",
            )
            worst = None
            episodes = []
            for log in heldout_logs:
                if not isinstance(log, dict):
                    continue
                rid = str(log.get("regime_id") or "")
                if not rid.startswith("nuisance_k2"):
                    continue
                ep_id = str(log.get("episode_id") or "")
                success_val = float(per_regime_success.get(rid, 0.0)) if isinstance(per_regime_success, dict) else 0.0
                if worst is None or success_val < worst:
                    worst = success_val
                episodes.append({"episode_id": ep_id, "regime_id": rid, "success": success_val})
            heldout_nuisance_check["episodes"] = episodes
            heldout_nuisance_check["worst_case_success"] = worst
    epoch_summary = {
        "format": "caoe_epoch_summary_v1",
        "schema_version": 1,
        "epoch_id": str(args.epoch_id),
        "epoch_num": epoch_num,
        "candidate_count": len(candidates),
        "selected_candidate_id": selected_candidate_id,
        "flags": flags,
        "degenerate_reason_counts": degenerate_reason_counts,
        "skipped_by_operator_counts": proposal_generation_summary.get("skipped_by_operator_counts") or {},
        "zero_regime_count": int(zero_regime_count),
        "regression_count": int(regression_count),
        "dev_classification": dev_classification,
        "dev_nuisance_gate_required": bool(dev_gate_required),
        "dev_nuisance_gate_episodes": dev_nuisance_gate_episodes,
        "dev_nuisance_gate_selected": dev_gate_selected,
        "heldout_nuisance_check": heldout_nuisance_check,
        "candidate_budget_by_family": budget_by_family,
        "candidate_budget_by_operator": proposal_generation_summary.get("candidate_budget_by_operator") or {},
    }
    _write_text_json(out_dir / "epoch_summary.json", epoch_summary)


def show_state(args: argparse.Namespace) -> None:
    state = load_state(args.state_dir)
    print(json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))


def replay_epoch(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    selection_path = out_dir / "selection.json"
    stored = _load_selection(selection_path)

    candidates_dir = out_dir / "candidates"
    cdel_results_dir = out_dir / "cdel_results_full"
    if not cdel_results_dir.exists():
        cdel_results_dir = out_dir / "cdel_results_screen"
    candidate_files = sorted([p for p in candidates_dir.iterdir() if p.name.endswith(".tar")])
    candidates = []
    for idx, _path in enumerate(candidate_files):
        local_meta = load_json(candidates_dir / f"candidate_{idx}_local_meta.json")
        candidates.append({"op_id": local_meta.get("op_id")})

    evaluations = _collect_evaluations(candidates, cdel_results_dir)
    evaluations_for_selection = evaluations
    gate_fail_ids: set[str] = set()
    decisions_path = out_dir / "candidate_decisions.json"
    if decisions_path.exists():
        decisions = _load_json(decisions_path)
        for entry in decisions.get("entries", []):
            if not isinstance(entry, dict):
                continue
            eligibility = entry.get("eligibility") or {}
            reasons = eligibility.get("ineligible_reason_codes") or []
            if "FAIL_DEV_NUISANCE_GATE" in reasons:
                cand_id = str(entry.get("candidate_id") or "")
                if cand_id:
                    gate_fail_ids.add(cand_id)
    if gate_fail_ids:
        evaluations_for_selection = [
            entry for entry in evaluations if str(entry.get("candidate_id") or "") not in gate_fail_ids
        ]
    recomputed_base = select_candidate(evaluations_for_selection)
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for cand_dir in sorted(cdel_results_dir.glob("candidate_*")):
        evidence_path = cand_dir / "evidence_report.json"
        if not evidence_path.exists():
            continue
        report = load_json(evidence_path)
        candidate_id = str(report.get("candidate_id") or "")
        if candidate_id:
            evidence_by_id[candidate_id] = report

    ordered_ids = [cand.get("candidate_id", "") for cand in candidates if cand.get("candidate_id")]
    candidates_evaluated: list[str] = []
    candidates_eligible: list[str] = []
    candidates_rejected: list[dict[str, Any]] = []
    for candidate_id in ordered_ids:
        report = evidence_by_id.get(candidate_id)
        reason_codes: list[str] = []
        if report is None:
            reason_codes.append("NO_EVIDENCE")
        else:
            candidates_evaluated.append(candidate_id)
            if report.get("format_error"):
                reason_codes.append("FORMAT_ERROR")
        eligible = report is not None and not report.get("format_error")
        if eligible:
            candidates_eligible.append(candidate_id)
        contracts = report.get("contracts") if report else {}
        contracts = contracts or {}
        for name, contract in (
            ("C-ANTI", contracts.get("C-ANTI") or {}),
            ("C-DO", contracts.get("C-DO") or {}),
            ("C-MDL", contracts.get("C-MDL") or {}),
            ("C-INV", contracts.get("C-INV") or {}),
            ("C-LIFE", contracts.get("C-LIFE") or {}),
        ):
            if contract.get("pass") is False:
                reason_codes.append(f"FAIL_{name}")
        decision = str(report.get("decision") or "FAIL") if report else "FAIL"
        if decision != "PASS":
            candidates_rejected.append({"candidate_id": candidate_id, "reason_codes": sorted(set(reason_codes))})

    recomputed = {
        "selected_candidate_id": recomputed_base.get("selected_candidate_id"),
        "candidates_evaluated": candidates_evaluated,
        "candidates_eligible": candidates_eligible,
        "candidates_rejected": candidates_rejected,
        "candidates_compared": candidates_eligible,
    }
    if recomputed != stored:
        raise SystemExit("selection mismatch in replay-epoch")


def apply_promotion(args: argparse.Namespace) -> None:
    epoch_dir = Path(args.epoch_dir)
    state_dir = Path(args.state_dir)
    epoch_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    selection = _load_json(epoch_dir / "selection.json")
    selected_id = args.selected_candidate_id or selection.get("selected_candidate_id")
    if not isinstance(selected_id, str) or selected_id == "none":
        raise SystemExit("selection is none")

    current_dir = state_dir / "current"
    base_onto_path = current_dir / "base_ontology.json"
    base_mech_path = current_dir / "base_mech.json"
    if not base_onto_path.exists() or not base_mech_path.exists():
        fallback_base = epoch_dir.parents[1] / "base"
        fb_onto = fallback_base / "base_ontology.json"
        fb_mech = fallback_base / "base_mech.json"
        if not fb_onto.exists() or not fb_mech.exists():
            raise SystemExit("base artifacts missing for promotion")
        current_dir.mkdir(parents=True, exist_ok=True)
        _write_text_json(base_onto_path, _load_json(fb_onto))
        _write_text_json(base_mech_path, _load_json(fb_mech))

    base_ontology = _load_json(base_onto_path)
    base_mech = _load_json(base_mech_path)
    parent_onto_hash = ontology_hash(base_ontology)
    parent_mech_hash = mechanism_hash(base_mech)

    cand_tar = None
    candidates_dir = epoch_dir / "candidates"
    for tar_path in sorted(candidates_dir.glob("candidate_*.tar")):
        with tarfile.open(tar_path, "r") as tar:
            try:
                manifest = json.loads(tar.extractfile("manifest.json").read())
            except Exception:
                continue
        if manifest.get("candidate_id") == selected_id:
            cand_tar = tar_path
            break
    if cand_tar is None:
        raise SystemExit("candidate tar not found for selected id")

    with tarfile.open(cand_tar, "r") as tar:
        patch = json.loads(tar.extractfile("ontology_patch.json").read())
        mech_diff = json.loads(tar.extractfile("mechanism_registry_diff.json").read())

    promoted_ontology = _apply_ontology_patch(base_ontology, patch)
    promoted_mech = _apply_mech_diff(base_mech, mech_diff)
    new_onto_hash = ontology_hash(promoted_ontology)
    promoted_ontology["ontology_hash"] = new_onto_hash
    if isinstance(promoted_mech, dict):
        promoted_mech["ontology_hash"] = new_onto_hash
    new_mech_hash = mechanism_hash(promoted_mech)

    current_dir.mkdir(parents=True, exist_ok=True)
    if args.atomic:
        _write_atomic(base_onto_path, promoted_ontology)
        _write_atomic(base_mech_path, promoted_mech)
    else:
        _write_text_json(base_onto_path, promoted_ontology)
        _write_text_json(base_mech_path, promoted_mech)

    receipt_path = epoch_dir / "receipts" / selected_id / "receipt.json"
    receipt_sha = _sha256_hex_file(receipt_path) if receipt_path.exists() else ""

    history_dir = state_dir / "history" / f"{selection.get('epoch_id', epoch_dir.name)}__{selected_id}"
    history_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "format": "caoe_promotion_record_v1_1",
        "schema_version": 1,
        "epoch_id": selection.get("epoch_id", epoch_dir.name),
        "selected_candidate_id": selected_id,
        "parent_base_hashes": {
            "ontology": parent_onto_hash,
            "mechanism": parent_mech_hash,
        },
        "new_base_hashes": {
            "ontology": new_onto_hash,
            "mechanism": new_mech_hash,
        },
        "receipt_sha256": receipt_sha,
        "epoch_artifacts_sha256": {
            "selection.json": _sha256_hex_file(epoch_dir / "selection.json"),
            "candidate_decisions.json": _sha256_hex_file(epoch_dir / "candidate_decisions.json"),
            "success_matrix.json": _sha256_hex_file(epoch_dir / "success_matrix.json"),
        },
    }
    _write_text_json(history_dir / "promotion_record.json", record)

    lifecycle_path = state_dir / "lifecycle.json"
    if lifecycle_path.exists():
        lifecycle = _load_json(lifecycle_path)
    else:
        lifecycle = {
            "format": "caoe_lifecycle_state_v1_1",
            "schema_version": 1,
            "stable_required": 2,
            "stable_run_count": 0,
            "state": "PROVISIONAL",
        }
    lifecycle["stable_run_count"] = 1
    lifecycle["state"] = "PROVISIONAL"
    lifecycle["last_epoch_id"] = selection.get("epoch_id", epoch_dir.name)
    lifecycle["current_candidate_id"] = selected_id
    _write_text_json(lifecycle_path, lifecycle)
    _write_sha256(state_dir / "lifecycle.sha256", _sha256_hex_file(lifecycle_path))


def _update_lifecycle_state(state_dir: Path, epoch_id: str, base_row: dict[str, Any]) -> None:
    lifecycle_path = state_dir / "lifecycle.json"
    if lifecycle_path.exists():
        lifecycle = _load_json(lifecycle_path)
    else:
        lifecycle = {
            "format": "caoe_lifecycle_state_v1_1",
            "schema_version": 1,
            "stable_required": 2,
            "stable_run_count": 0,
            "state": "PROVISIONAL",
        }
    all_success = all(float(v) >= 1.0 for v in base_row.values()) if base_row else False
    if all_success:
        lifecycle["stable_run_count"] = int(lifecycle.get("stable_run_count", 0)) + 1
    else:
        lifecycle["stable_run_count"] = 0
    lifecycle["state"] = "STABLE" if lifecycle["stable_run_count"] >= int(lifecycle.get("stable_required", 2)) else "PROVISIONAL"
    lifecycle["last_epoch_id"] = epoch_id
    _write_text_json(lifecycle_path, lifecycle)
    _write_sha256(state_dir / "lifecycle.sha256", _sha256_hex_file(lifecycle_path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="caoe_proposer_cli_v1")
    sub = parser.add_subparsers(dest="command", required=True)

    run_epoch_p = sub.add_parser("run-epoch")
    run_epoch_p.add_argument("--epoch_id", required=True)
    run_epoch_p.add_argument("--base_ontology", required=True)
    run_epoch_p.add_argument("--base_mech", required=True)
    run_epoch_p.add_argument("--suitepack_dev", required=True)
    run_epoch_p.add_argument("--suitepack_heldout", required=True)
    run_epoch_p.add_argument("--heldout_suite_id", required=True)
    run_epoch_p.add_argument("--cdel_bin", required=True)
    run_epoch_p.add_argument("--state_dir", required=True)
    run_epoch_p.add_argument("--out_dir", required=True)
    run_epoch_p.add_argument("--max_candidates", type=int, default=32)
    run_epoch_p.add_argument("--eval_plan", choices=["full", "screen"], default="full")
    run_epoch_p.add_argument("--screen_dev_episodes", type=int, default=32)
    run_epoch_p.add_argument("--screen_heldout_episodes", type=int, default=64)
    run_epoch_p.add_argument("--full_top_k", type=int, default=2)
    run_epoch_p.add_argument("--workers", type=int, default=2)
    run_epoch_p.add_argument("--progress_interval", type=int, default=8)
    run_epoch_p.add_argument("--dev_oracle_sequence")
    run_epoch_p.add_argument("--dev_oracle_memoryless")
    run_epoch_p.add_argument("--dev_oracle_depth2")
    run_epoch_p.set_defaults(func=run_epoch)

    show_state_p = sub.add_parser("show-state")
    show_state_p.add_argument("--state_dir", required=True)
    show_state_p.set_defaults(func=show_state)

    replay_p = sub.add_parser("replay-epoch")
    replay_p.add_argument("--out_dir", required=True)
    replay_p.set_defaults(func=replay_epoch)

    promote_p = sub.add_parser("apply-promotion")
    promote_p.add_argument("--epoch_dir", required=True)
    promote_p.add_argument("--state_dir", required=True)
    promote_p.add_argument("--selected_candidate_id", default=None)
    promote_p.add_argument("--atomic", type=lambda v: str(v).lower() != "false", default=True)
    promote_p.set_defaults(func=apply_promotion)

    return parser


def main(argv: list[str] | None = None) -> None:
    bootstrap_paths()
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
