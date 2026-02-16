"""Wake anomaly mining for CAOE v1 (certified evidence only)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[1]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from api_v1 import load_json, write_json  # noqa: E402
from artifacts.candidate_manifest_builder_v1 import build_manifest  # noqa: E402
from artifacts.candidate_tar_writer_v1 import build_candidate_tar_bytes  # noqa: E402
from artifacts.ids_v1 import mechanism_hash, ontology_hash  # noqa: E402
from dawn.cdel_client_v1 import run_cdel_verify  # noqa: E402
from wake.dev_diagnostics_v1_2 import build_failure_signatures, build_witness_trace  # noqa: E402


class WakeError(ValueError):
    pass


def _extract_nested(report: dict[str, Any], path: list[str]) -> Any:
    cur: Any = report
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _require_value(report: dict[str, Any], paths: list[list[str]], label: str) -> Any:
    for path in paths:
        value = _extract_nested(report, path)
        if value is not None:
            return value
    raise WakeError(f"missing required evidence field: {label}")


def _extract_base_metrics(report: dict[str, Any]) -> dict[str, Any]:
    per_regime_success = _require_value(
        report,
        [["base_metrics", "c_inv", "per_regime_success"]],
        "base_metrics.c_inv.per_regime_success",
    )
    per_regime_efficiency = _require_value(
        report,
        [["base_metrics", "c_inv", "per_regime_efficiency"]],
        "base_metrics.c_inv.per_regime_efficiency",
    )
    per_family = _require_value(
        report,
        [["base_metrics", "c_inv", "per_family"]],
        "base_metrics.c_inv.per_family",
    )
    heldout_mdl_bits = _require_value(
        report,
        [["base_metrics", "c_mdl", "heldout_tml_bits"]],
        "base_metrics.c_mdl.heldout_tml_bits",
    )
    heldout_worst_case_success = _require_value(
        report,
        [["base_metrics", "c_inv", "heldout_worst_case_success"]],
        "base_metrics.c_inv.heldout_worst_case_success",
    )
    heldout_worst_case_efficiency = _require_value(
        report,
        [["base_metrics", "c_inv", "heldout_worst_case_efficiency"]],
        "base_metrics.c_inv.heldout_worst_case_efficiency",
    )
    leakage_sensitivity = _require_value(
        report,
        [["base_metrics", "c_anti", "leakage_sensitivity"]],
        "base_metrics.c_anti.leakage_sensitivity",
    )
    relabel_sensitivity = _require_value(
        report,
        [["base_metrics", "c_anti", "relabel_sensitivity"]],
        "base_metrics.c_anti.relabel_sensitivity",
    )
    if not isinstance(per_regime_success, dict) or not isinstance(per_regime_efficiency, dict):
        raise WakeError("per-regime metrics invalid")
    return {
        "per_regime_success": per_regime_success,
        "per_regime_efficiency": per_regime_efficiency,
        "per_family": per_family if isinstance(per_family, dict) else {},
        "heldout_mdl_bits": heldout_mdl_bits,
        "heldout_worst_case_success": heldout_worst_case_success,
        "heldout_worst_case_efficiency": heldout_worst_case_efficiency,
        "leakage_sensitivity": leakage_sensitivity,
        "relabel_sensitivity": relabel_sensitivity,
    }


def _build_identity_patch(base_ontology: dict[str, Any], requires_c_do: bool) -> dict[str, Any]:
    return {
        "format": "ontology_patch_v1_1",
        "schema_version": 1,
        "base_ontology_hash": ontology_hash(base_ontology),
        "isa_version": str(base_ontology.get("isa_version") or "caoe_absop_isa_v1_2"),
        "ops": [],
        "claimed_obligations": {
            "requires_c_do": bool(requires_c_do),
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


def _build_identity_mech_diff(base_mech_hash: str) -> dict[str, Any]:
    return {
        "format": "mechanism_registry_diff_v1_1",
        "schema_version": 1,
        "base_mech_hash": base_mech_hash,
        "ops": [],
    }


def run_identity_and_mine(
    *,
    base_ontology: dict[str, Any],
    base_mech: dict[str, Any],
    base_ontology_path: str | Path,
    base_mech_path: str | Path,
    suite_id_dev: str,
    suite_id_heldout: str,
    suitepack_dev_path: str | Path,
    suitepack_heldout_path: str | Path,
    cdel_bin: str | Path,
    epoch_id: str,
    out_dir: str | Path,
    eval_plan: str = "full",
    screen_dev_episodes: int = 32,
    screen_heldout_episodes: int = 64,
    no_logs_on_fail: bool = False,
    progress_interval: int = 8,
    progress_path: str | Path | None = None,
    require_dev_diagnostics: bool = True,
) -> tuple[dict[str, Any], str]:
    cache_dir_env = os.environ.get("CAOE_IDENTITY_CACHE_DIR")
    cache_dir = Path(cache_dir_env).resolve() if cache_dir_env else None
    if cache_dir is not None and cache_dir.exists():
        evidence_path = cache_dir / "evidence_report.json"
        receipt_path = cache_dir / "receipt.json"
        anomaly_path = cache_dir / "anomaly_buffer.json"
        if not evidence_path.exists() or not receipt_path.exists() or not anomaly_path.exists():
            raise WakeError("identity cache missing required files")
        report = load_json(evidence_path)
        anomaly_buffer = load_json(anomaly_path)
        if isinstance(anomaly_buffer, dict):
            signals = anomaly_buffer.get("signals")
            if isinstance(signals, dict) and "worst_families" not in signals:
                signals["worst_families"] = []
            if require_dev_diagnostics and "failure_signatures" not in anomaly_buffer:
                anomaly_buffer = None
        candidate_id = report.get("candidate_id")
        if anomaly_buffer is not None and isinstance(candidate_id, str) and candidate_id:
            return anomaly_buffer, candidate_id

    base_ontology_hash = ontology_hash(base_ontology)
    base_mech_hash = mechanism_hash(base_mech)
    ontology_patch = _build_identity_patch(
        base_ontology,
        bool(base_ontology.get("supports_macro_do", False)),
    )
    mech_diff = _build_identity_mech_diff(base_mech_hash)
    programs_by_path: dict[str, bytes] = {}
    manifest = build_manifest(
        base_ontology=base_ontology,
        base_mech=base_mech,
        suite_id_dev=suite_id_dev,
        suite_id_heldout=suite_id_heldout,
        claimed_supports_macro_do=bool(base_ontology.get("supports_macro_do", False)),
        ontology_patch=ontology_patch,
        mechanism_diff=mech_diff,
        programs_by_path=programs_by_path,
    )
    candidate_id = manifest["candidate_id"]
    tar_bytes = build_candidate_tar_bytes(manifest, ontology_patch, mech_diff, programs_by_path)

    receipt_data: dict[str, Any] | None = None
    dev_logs: list[dict[str, Any]] = []
    suitepack_dev = None
    suitepack_dev_path = Path(suitepack_dev_path)
    if require_dev_diagnostics:
        try:
            suitepack_dev = load_json(suitepack_dev_path)
        except Exception:
            suitepack_dev = None
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        candidate_tar = tmpdir_path / "identity_candidate.tar"
        candidate_tar.write_bytes(tar_bytes)
        candidate_out_dir = tmpdir_path / "cdel_out"
        run_cdel_verify(
            cdel_bin=cdel_bin,
            candidate_tar=candidate_tar,
            base_ontology=Path(base_ontology_path),
            base_mech=Path(base_mech_path),
            suitepack_dev=Path(suitepack_dev_path),
            suitepack_heldout=Path(suitepack_heldout_path),
            out_dir=candidate_out_dir,
            eval_plan=eval_plan,
            screen_dev_episodes=screen_dev_episodes,
            screen_heldout_episodes=screen_heldout_episodes,
            no_logs_on_fail=no_logs_on_fail,
            progress_interval=progress_interval,
            progress_path=progress_path,
        )
        evidence_path = candidate_out_dir / "evidence_report.json"
        if not evidence_path.exists():
            raise WakeError("CDEL did not produce evidence_report.json for identity candidate")
        report = load_json(evidence_path)
        receipt_path = candidate_out_dir / "receipt.json"
        if receipt_path.exists():
            receipt_data = load_json(receipt_path)
        if require_dev_diagnostics:
            refs = (report.get("artifacts") or {}).get("intervention_logs") or []
            for ref in refs:
                if not isinstance(ref, dict):
                    continue
                if ref.get("suite_track") != "dev" or ref.get("variant") != "base":
                    continue
                rel = ref.get("relative_path")
                if not rel:
                    continue
                log_path = candidate_out_dir / str(rel)
                if not log_path.exists():
                    continue
                try:
                    dev_logs.append(load_json(log_path))
                except Exception:
                    continue

    base_metrics = _extract_base_metrics(report)
    per_success = base_metrics["per_regime_success"]
    per_eff = base_metrics["per_regime_efficiency"]
    per_family = base_metrics.get("per_family") or {}
    regime_entries = []
    for regime_id in sorted(per_success.keys()):
        if regime_id not in per_eff:
            raise WakeError("per-regime efficiency missing for regime")
        success = per_success[regime_id]
        efficiency = per_eff[regime_id]
        regime_entries.append({"regime_id": regime_id, "success": success, "efficiency": efficiency})
    regime_entries.sort(key=lambda x: (x["success"], x["efficiency"], x["regime_id"]))
    worst_regimes = regime_entries[:8]

    family_entries = []
    for family_id in sorted(per_family.keys()):
        entry = per_family.get(family_id) or {}
        avg_success = float(entry.get("avg_success", 0.0))
        avg_eff = float(entry.get("avg_efficiency", 0.0))
        regime_ids = entry.get("regimes_evaluated") or []
        fam_regimes = []
        for rid in regime_ids:
            if rid not in per_success or rid not in per_eff:
                continue
            fam_regimes.append(
                {
                    "regime_id": rid,
                    "success": per_success[rid],
                    "efficiency": per_eff[rid],
                }
            )
        fam_regimes.sort(key=lambda x: (x["success"], x["efficiency"], x["regime_id"]))
        family_entries.append(
            {
                "family_id": family_id,
                "avg_success": avg_success,
                "avg_efficiency": avg_eff,
                "worst_regimes": fam_regimes[:4],
            }
        )
    family_entries.sort(key=lambda x: (x["avg_success"], x["avg_efficiency"], x["family_id"]))
    worst_families = family_entries[:4]

    anomaly_buffer = {
        "format": "caoe_anomaly_buffer_v1",
        "schema_version": 1,
        "epoch_id": str(epoch_id),
        "base_ontology_hash": base_ontology_hash,
        "identity_candidate_id": candidate_id,
        "signals": {
            "worst_regimes": worst_regimes,
            "worst_families": worst_families,
            "global": {
                "heldout_worst_case_success": base_metrics["heldout_worst_case_success"],
                "heldout_worst_case_efficiency": base_metrics["heldout_worst_case_efficiency"],
                "heldout_mdl_bits": int(base_metrics["heldout_mdl_bits"]),
                "leakage_sensitivity": base_metrics["leakage_sensitivity"],
                "relabel_sensitivity": base_metrics["relabel_sensitivity"],
            },
        },
    }
    if require_dev_diagnostics and dev_logs and isinstance(suitepack_dev, dict):
        nuisance_regimes = {
            str(item.get("regime_id") or "")
            for item in worst_regimes
            if isinstance(item, dict) and str(item.get("regime_id") or "").startswith("nuisance")
        }
        failure_signatures = build_failure_signatures(
            base_ontology=base_ontology,
            suitepack_dev=suitepack_dev,
            dev_logs=dev_logs,
            regime_filter=sorted(rid for rid in nuisance_regimes if rid),
        )
        if failure_signatures:
            anomaly_buffer["failure_signatures"] = failure_signatures
        trace = build_witness_trace(
            base_ontology=base_ontology,
            suitepack_dev=suitepack_dev,
            dev_logs=dev_logs,
            regime_id="nuisance_k2_00",
        )
        if trace is not None:
            out_dir_path = Path(out_dir)
            trace_path = out_dir_path / "dev_witness_traces" / "nuisance_k2_00.trace.json"
            write_json(trace_path, trace)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        write_json(cache_dir / "evidence_report.json", report)
        if receipt_data is not None:
            write_json(cache_dir / "receipt.json", receipt_data)
        else:
            raise WakeError("receipt.json missing from identity verify")
        write_json(cache_dir / "anomaly_buffer.json", anomaly_buffer)
    return anomaly_buffer, candidate_id
