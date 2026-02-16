"""Epoch execution helpers for v1.5r."""

from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .barrier import advance_barrier_state, barrier_scalar, build_barrier_record
from .canon import (
    CanonError,
    canon_bytes,
    hash_json,
    load_canon_json,
    loads,
    sha256_prefixed,
    write_canon_json,
    write_jsonl_line,
)
from .cmeta.work_meter import (
    WorkMeter,
    bump_short_circuits,
    bump_verifier_gas,
    compare_workvec,
    set_current_meter,
)
from .constants import meta_identities, require_constants
from .ctime.eviction import compute_macro_evictions
from .ctime.macro import admit_macro, load_macro_defs, load_macro_ledger, update_macro_ledger, write_macro_active_set
from .ctime.tokenization import build_macro_tokenization_report, build_rho_report
from .cmeta.translation import load_benchmark_pack, translate_validate
from .ctime.trace import load_trace_jsonl
from .eval_runner import eval_instance
from .family_semantics import build_family_semantics_report
from .family_dsl.runtime import compute_signature, instantiate_family, validate_family_relaxed
from .proposals.inbox import (
    load_family_proposals,
    load_macro_proposals,
    load_mech_patch_proposals,
    load_meta_patch_proposals,
)
from .promotion import dominance_decision, tiebreak_key
from .rsi_tracker import update_rsi_tracker
from .rsi_integrity_tracker import update_rsi_integrity_tracker
from .rsi_portfolio_tracker import update_rsi_portfolio_tracker
from .sr_cegar.frontier import compress_frontier
from .sr_cegar.gates import learnability_pass, novelty_pass
from .sr_cegar.witness import build_failure_witness, shrink_trace
from .sr_cegar.witness_ledger import (
    append_ledger_line,
    build_ledger_line,
    load_ledger_lines,
    witness_hashes_from_ledger,
    verify_ledger_chain,
    write_ledger_head,
)
from .suites.anchor import build_anchor_pack
from .suites.pressure import build_pressure_pack
from .suites.thermostat import update_pressure_schedule


def _hash_file(path: Path) -> str:
    if path.suffix == ".json":
        payload = load_canon_json(path)
        return sha256_prefixed(canon_bytes(payload))
    return sha256_prefixed(path.read_bytes())


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _meta_core_root() -> Path:
    env = os.environ.get("META_CORE_ROOT")
    if env:
        return Path(env)
    return _repo_root() / "meta-core"


def derive_epoch_key(
    master_key: bytes,
    epoch_id: str,
    base_state_hashes: dict[str, str],
    frontier_hash: str,
) -> bytes:
    payload = {
        "epoch_id": epoch_id,
        "base_state_hashes": base_state_hashes,
        "frontier_hash": frontier_hash,
    }
    material = master_key + b"epoch_key_v1" + canon_bytes(payload)
    return hashlib.sha256(material).digest()


def build_epoch_commit(
    *,
    epoch_id: str,
    base_state_hashes: dict[str, str],
    frontier_hash: str,
    master_key: bytes,
    created_unix_ms: int,
) -> dict[str, Any]:
    k_t = derive_epoch_key(master_key, epoch_id, base_state_hashes, frontier_hash)
    c_t = sha256_prefixed(hashlib.sha256(k_t).digest())
    return {
        "schema": "epoch_commit_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "commitment": c_t,
        "frontier_hash": frontier_hash,
        "base_state_hashes": base_state_hashes,
        "created_unix_ms": created_unix_ms,
    }


def _load_state_hashes(state_dir: Path) -> dict[str, str]:
    required = {
        "base_ontology_hash": state_dir / "current" / "base_ontology.json",
        "base_mech_hash": state_dir / "current" / "base_mech.json",
        "frontier_hash": state_dir / "current" / "frontier_v1.json",
        "macro_active_set_hash": state_dir / "current" / "macro_active_set_v1.json",
        "macro_ledger_hash": state_dir / "current" / "macro_ledger_v1.jsonl",
        "pressure_schedule_hash": state_dir / "current" / "pressure_schedule_v1.json",
        "meta_patch_set_hash": state_dir / "current" / "meta_patch_set_v1.json",
    }
    hashes = {}
    for key, path in required.items():
        if not path.exists():
            raise FileNotFoundError(f"missing state file: {path}")
        hashes[key] = _hash_file(path)
    return hashes


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _signature_from_reference(state_dir: Path, fam_hash: str | None) -> dict[str, Any]:
    if fam_hash:
        fam_path = state_dir / "current" / "families" / f"{fam_hash.split(':', 1)[1]}.json"
        if fam_path.exists():
            try:
                family_obj = load_canon_json(fam_path)
                return compute_signature(family_obj)
            except Exception:
                pass
    return compute_signature({"family_hash": fam_hash or ""})


def _list_epoch_dirs(state_dir: Path, out_dir: Path) -> list[Path]:
    epochs_dir = state_dir / "epochs"
    entries: list[Path] = []
    if epochs_dir.exists():
        entries = [p for p in epochs_dir.iterdir() if p.is_dir()]
    entries.append(out_dir)
    return sorted(entries, key=lambda p: p.name)


def _load_jsonl_payloads(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payloads: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        payload = loads(raw)
        if canon_bytes(payload).decode("utf-8") != raw:
            raise CanonError("non-canonical jsonl line")
        if not isinstance(payload, dict):
            raise CanonError("jsonl payload must be object")
        payloads.append(payload)
    return payloads


def _load_state_ledger_events(state_dir: Path) -> dict[str, dict[str, Any]]:
    ledger_path = state_dir / "current" / "state_ledger_v1.jsonl"
    events: dict[str, dict[str, Any]] = {}
    if not ledger_path.exists():
        return events
    prev_hash = "sha256:" + "0" * 64
    for raw in ledger_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        payload = loads(raw)
        if canon_bytes(payload).decode("utf-8") != raw:
            raise CanonError("non-canonical state ledger line")
        if payload.get("prev_ledger_hash") != prev_hash:
            raise CanonError("state ledger chain mismatch")
        prev_hash = payload.get("line_hash")
        epoch_id = payload.get("epoch_id")
        if isinstance(epoch_id, str):
            events[epoch_id] = payload
    return events


def _load_barrier_record(epoch_dir: Path) -> dict[str, Any] | None:
    path = epoch_dir / "barrier_record_v1.json"
    if path.exists():
        return load_canon_json(path)
    diag_path = epoch_dir / "diagnostics" / "barrier_record_v1.json"
    if diag_path.exists():
        return load_canon_json(diag_path)
    return None


def _bundle_hash(manifest: dict[str, Any], blobs: dict[str, bytes]) -> str:
    payload = dict(manifest)
    payload.pop("bundle_hash", None)
    manifest_bytes = canon_bytes(payload)
    parts = [manifest_bytes]
    for blob_hash in sorted(blobs.keys()):
        parts.append(blobs[blob_hash])
    return sha256_prefixed(b"".join(parts))


def _write_promotion_bundle(
    *,
    diagnostics_dir: Path,
    candidate: dict[str, Any],
    meta: dict[str, str],
) -> tuple[Path, dict[str, Any]]:
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str):
        raise ValueError("candidate_id missing for promotion bundle")
    bundle_dir = diagnostics_dir / "promotion_bundle" / candidate_id.split(":", 1)[1]
    bundle_dir.mkdir(parents=True, exist_ok=True)
    blobs_dir = bundle_dir / "blobs"
    blobs_dir.mkdir(parents=True, exist_ok=True)

    blobs: list[dict[str, Any]] = []
    blob_bytes: dict[str, bytes] = {}

    def _emit_blob(name: str, source_path: Path | None, content: str | None = None) -> tuple[str, int]:
        if source_path and source_path.exists():
            if source_path.suffix == ".json":
                payload = load_canon_json(source_path)
                data = canon_bytes(payload)
            else:
                data = source_path.read_bytes()
            blob_path = blobs_dir / source_path.name
            blob_path.write_bytes(data)
        else:
            data = (content or "").encode("utf-8")
            blob_path = blobs_dir / f"{name}.txt"
            blob_path.write_bytes(data)
        blob_hash = sha256_prefixed(data)
        blobs.append({"path": str(blob_path.relative_to(bundle_dir)), "sha256": blob_hash, "bytes": len(data)})
        blob_bytes[blob_hash] = data
        return blob_hash, len(data)

    promotion_type = candidate.get("promotion_type")
    for entry in candidate.get("delta_artifacts", []):
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        path = None
        if name == "frontier_v1_next.json":
            path = diagnostics_dir / "frontier_v1_next.json"
        elif name == "frontier_update_report_v1.json":
            path = diagnostics_dir / "frontier_update_report_v1.json"
        elif name == "pressure_schedule_next_v1.json":
            path = diagnostics_dir / "pressure_schedule_next_v1.json"
        elif name == "macro_def":
            macro_id = candidate.get("meta", {}).get("macro_id")
            if isinstance(macro_id, str):
                path = diagnostics_dir / "candidate_macros" / f"{macro_id.split(':', 1)[1]}.json"
        elif name == "macro_admission_report_v1.json":
            path = diagnostics_dir / "macro_admission_report_v1.json"
        elif name == "macro_eviction_report_v1.json":
            path = diagnostics_dir / "macro_eviction_report_v1.json"
        elif name == "macro_id":
            macro_id = candidate.get("meta", {}).get("macro_id")
            _emit_blob(name, None, content=str(macro_id or ""))
            continue
        elif name == "meta_patch":
            patch_id = candidate.get("meta", {}).get("patch_id")
            if isinstance(patch_id, str):
                path = diagnostics_dir / "candidate_meta_patches" / f"{patch_id.split(':', 1)[1]}.json"
        elif name == "mech_patch":
            patch_id = candidate.get("meta", {}).get("patch_id")
            if isinstance(patch_id, str):
                path = diagnostics_dir / "candidate_mech_patches" / f"{patch_id.split(':', 1)[1]}.json"
        elif name == "translation_cert_v1.json":
            cert_rel = candidate.get("meta", {}).get("translation_cert_path")
            if isinstance(cert_rel, str):
                path = diagnostics_dir / cert_rel
        if path is None and promotion_type in {"meta_patch", "mech_patch"}:
            continue
        _emit_blob(name, path)

    witness_path = diagnostics_dir / "dominance_witness_v1.json"
    if not witness_path.exists():
        raise CanonError("dominance_witness_v1.json missing for promotion bundle")
    dominance_witness_hash, _ = _emit_blob("dominance_witness_v1.json", witness_path)

    manifest = {
        "schema": "promotion_bundle_manifest_v1",
        "schema_version": 1,
        "promotion_type": promotion_type,
        "META_HASH": meta.get("META_HASH"),
        "KERNEL_HASH": meta.get("KERNEL_HASH"),
        "constants_hash": meta.get("constants_hash"),
        "proofs": {
            "dominance_witness_hash": dominance_witness_hash,
        },
        "blobs": blobs,
    }
    manifest["bundle_hash"] = _bundle_hash(manifest, blob_bytes)
    (bundle_dir / "promotion_bundle_manifest_v1.json").write_bytes(canon_bytes(manifest))
    return bundle_dir, manifest




def run_epoch(
    *,
    epoch_id: str,
    base_ontology: Path,
    base_mech: Path,
    state_dir: Path,
    out_dir: Path,
    master_key_b64: str,
    created_unix_ms: int | None,
    strict_rsi: bool = False,
    strict_integrity: bool = False,
    strict_portfolio: bool = False,
) -> None:
    constants = require_constants()
    meta = meta_identities()
    _ensure_dir(out_dir)
    _ensure_dir(out_dir / "diagnostics")
    _ensure_dir(out_dir / "receipts")
    _ensure_dir(out_dir / "traces")
    # Work meter starts at epoch entry (counts gating + eval + promotion work).
    meter = WorkMeter(epoch_id, "sha256:" + "0" * 64)
    set_current_meter(meter)

    load_canon_json(base_ontology)
    base_mech_obj = load_canon_json(base_mech)
    current_state_head_hash = None
    state_head_path = state_dir / "current" / "state_ledger_head_v1.json"
    if state_head_path.exists():
        state_head = load_canon_json(state_head_path)
        if isinstance(state_head.get("ledger_head_hash"), str):
            current_state_head_hash = state_head.get("ledger_head_hash")

    def _apply_mech_patch(base_mech_payload: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        policy_program = patch.get("policy_program")
        if not isinstance(policy_program, dict):
            raise CanonError("mech_patch missing policy_program")
        policy_name = policy_program.get("name")
        if not isinstance(policy_name, str):
            raise CanonError("mech_patch policy_program missing name")
        mech = dict(base_mech_payload)
        definitions = list(mech.get("definitions", [])) if isinstance(mech.get("definitions"), list) else []
        definitions = [item for item in definitions if item.get("name") != policy_name]
        definitions.append(policy_program)
        mech["definitions"] = definitions
        mech["candidate_symbol"] = policy_name
        mech["baseline_symbol"] = policy_name
        mech["oracle_symbol"] = policy_name
        return mech

    base_state_hashes = _load_state_hashes(state_dir)
    frontier_path = state_dir / "current" / "frontier_v1.json"
    frontier = load_canon_json(frontier_path)
    frontier_hash = base_state_hashes["frontier_hash"]
    family_hash_by_id = {entry.get("family_id"): entry.get("family_hash") for entry in frontier.get("families", [])}
    registry_path = state_dir / "current" / "family_registry_v1.json"
    registry = {}
    if registry_path.exists():
        registry = load_canon_json(registry_path)
    if not isinstance(registry, dict):
        registry = {}
    changed_registry = False
    for fid, fh in family_hash_by_id.items():
        if fid and fh and registry.get(fid) != fh:
            registry[fid] = fh
            changed_registry = True
    if changed_registry or not registry_path.exists():
        write_canon_json(registry_path, registry)

    if created_unix_ms is None:
        created_unix_ms = 0

    master_key = base64.b64decode(master_key_b64)
    if len(master_key) != 32:
        raise CanonError("CDEL_SEALED_PRIVKEY must decode to 32 bytes")

    k_t = derive_epoch_key(master_key, epoch_id, base_state_hashes, frontier_hash)
    epoch_commit = build_epoch_commit(
        epoch_id=epoch_id,
        base_state_hashes=base_state_hashes,
        frontier_hash=frontier_hash,
        master_key=master_key,
        created_unix_ms=created_unix_ms,
    )
    epoch_commit["x-meta"] = meta
    write_canon_json(out_dir / "epoch_commit_v1.json", epoch_commit)

    families: list[dict[str, Any]] = []
    family_objs: list[dict[str, Any]] = []
    for entry in frontier.get("families", []):
        fam_id = entry.get("family_id")
        fam_hash = entry.get("family_hash")
        signature = _signature_from_reference(state_dir, fam_hash)
        if fam_id:
            families.append({"family_id": fam_id, "signature": signature})
        if fam_hash:
            fam_path = state_dir / "current" / "families" / f"{fam_hash.split(':', 1)[1]}.json"
            if fam_path.exists():
                try:
                    family_obj = load_canon_json(fam_path)
                    family_objs.append(family_obj)
                except Exception:
                    continue

    diagnostics_dir = out_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    # SR-CEGAR: consider untrusted family proposals (inbox)
    admitted_family: dict[str, Any] | None = None
    admitted_semantics_report: dict[str, Any] | None = None
    last_semantics_report: dict[str, Any] | None = None
    witness_hashes: set[str] = set()
    ledger_path = state_dir / "current" / "witness_ledger_v1.jsonl"
    ledger_lines = load_ledger_lines(ledger_path)
    if ledger_lines:
        verify_ledger_chain(ledger_lines)
        witness_hashes = witness_hashes_from_ledger(ledger_lines)
    for candidate in load_family_proposals(state_dir):
        validate_family_relaxed(candidate)
        parent_hash = candidate.get("x-parent_witness_hash")
        parent_ok = isinstance(parent_hash, str) and parent_hash in witness_hashes
        semantics_report = build_family_semantics_report(
            epoch_id=epoch_id,
            family=candidate,
            prev_frontier_families=family_objs,
        )
        checks = semantics_report.get("checks", {}) if isinstance(semantics_report, dict) else {}
        if isinstance(checks, dict):
            checks["parent_witness_present"] = {
                "ok": bool(parent_ok),
                "reason_codes": [] if parent_ok else ["FAMILY_MISSING_PARENT_WITNESS"],
            }
        semantics_report["checks"] = checks
        semantics_report["x-meta"] = meta
        last_semantics_report = semantics_report
        key_sensitive_ok = bool(checks.get("key_sensitive", {}).get("ok")) if isinstance(checks, dict) else False
        fingerprint_ok = bool(checks.get("fingerprint_unique_vs_prev_frontier", {}).get("ok")) if isinstance(checks, dict) else False
        signature_ok = bool(checks.get("signature_matches_recomputed", {}).get("ok")) if isinstance(checks, dict) else False
        if not (parent_ok and key_sensitive_ok and fingerprint_ok and signature_ok):
            continue
        nov_ok, _min_dist = novelty_pass(candidate, families)
        learn_ok = learnability_pass(
            candidate,
            epoch_id=epoch_id,
            epoch_commit=epoch_commit,
            k_t=k_t,
            diagnostics_dir=str(diagnostics_dir),
        )
        if nov_ok and learn_ok:
            admitted_family = candidate
            admitted_semantics_report = semantics_report
            break

    candidate_families = list(families)
    candidate_family_objs = list(family_objs)
    next_frontier: dict[str, Any] | None = None
    if admitted_family:
        candidate_families.append({"family_id": admitted_family["family_id"], "signature": admitted_family["signature"]})
        candidate_family_objs.append(admitted_family)

    compressed, frontier_report = compress_frontier(candidate_families, [], int(constants["sr"]["m_frontier"]))
    if admitted_family:
        frontier_report["admitted_family_id"] = admitted_family.get("family_id")
    write_canon_json(diagnostics_dir / "frontier_update_report_v1.json", frontier_report)

    if admitted_family:
        admitted_hash = hash_json(admitted_family)
        family_hash_by_id[admitted_family["family_id"]] = admitted_hash
        candidate_dir = diagnostics_dir / "candidate_families"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        write_canon_json(candidate_dir / f"{admitted_hash.split(':', 1)[1]}.json", admitted_family)
        next_families = []
        for fam in compressed:
            fam_id = fam.get("family_id")
            fam_hash = family_hash_by_id.get(fam_id)
            if fam_id and fam_hash:
                next_families.append({"family_id": fam_id, "family_hash": fam_hash})
        next_frontier = {
            "schema": "frontier_v1",
            "schema_version": 1,
            "frontier_id": "",
            "families": next_families,
            "M_FRONTIER": int(constants["sr"]["m_frontier"]),
            "signature_version": 1,
            "compression_proof_hash": _hash_file(diagnostics_dir / "frontier_update_report_v1.json"),
        }
        next_frontier["frontier_id"] = hash_json({k: v for k, v in next_frontier.items() if k != "frontier_id"})
        write_canon_json(diagnostics_dir / "frontier_v1_next.json", next_frontier)

    if admitted_semantics_report is not None:
        write_canon_json(diagnostics_dir / "family_semantics_report_v1.json", admitted_semantics_report)
    elif last_semantics_report is not None:
        write_canon_json(diagnostics_dir / "family_semantics_report_v1.json", last_semantics_report)

    # Build anchor/pressure packs (deterministic, pinned constants)
    n_anchor = int(constants["sr"]["n_anchor_per_family"])
    n_pressure = int(constants["sr"]["n_pressure_per_family"])
    pressure_schedule_path = state_dir / "current" / "pressure_schedule_v1.json"
    pressure_schedule = load_canon_json(pressure_schedule_path)
    pressure_level = int(pressure_schedule.get("p_t", 0))
    anchor_pack_path = state_dir / "current" / "anchor_pack_v1.json"
    if not anchor_pack_path.exists():
        raise FileNotFoundError(f"missing anchor pack: {anchor_pack_path}")
    anchor_pack = load_canon_json(anchor_pack_path)
    # Ensure families referenced by anchor pack are loaded (stationary anchor support)
    existing_ids = {fam.get("family_id") for fam in family_objs if isinstance(fam.get("family_id"), str)}
    for entry in anchor_pack.get("families", []):
        fam_id = entry.get("family_id")
        if not isinstance(fam_id, str) or fam_id in existing_ids:
            continue
        fam_hash = registry.get(fam_id) or family_hash_by_id.get(fam_id)
        if not isinstance(fam_hash, str):
            raise CanonError("anchor_pack references unknown family_id")
        fam_path = state_dir / "current" / "families" / f"{fam_hash.split(':', 1)[1]}.json"
        if not fam_path.exists():
            raise FileNotFoundError(f"missing family file for anchor pack: {fam_path}")
        family_obj = load_canon_json(fam_path)
        family_objs.append(family_obj)
        existing_ids.add(fam_id)
    pressure_pack = build_pressure_pack(
        frontier_hash=frontier_hash,
        families=family_objs,
        n_per_family=n_pressure,
        pressure_level=pressure_level,
    )
    anchor_pack["x-meta"] = meta
    pressure_pack["x-meta"] = meta
    write_canon_json(diagnostics_dir / "anchor_pack_v1.json", anchor_pack)
    write_canon_json(diagnostics_dir / "pressure_pack_v1.json", pressure_pack)

    # Trace outputs (heldout + dev)
    trace_dev = out_dir / "traces" / "trace_dev_v1.jsonl"
    trace_hold = out_dir / "traces" / "trace_heldout_v1.jsonl"
    if trace_dev.exists():
        trace_dev.unlink()
    if trace_hold.exists():
        trace_hold.unlink()
    trace_dev.touch()
    trace_hold.touch()

    family_by_id = {fam.get("family_id"): fam for fam in family_objs if isinstance(fam.get("family_id"), str)}

    def _eval_pack(
        pack: dict[str, Any],
        *,
        record_traces: bool = True,
        record_specs: bool = True,
        family_lookup: dict[str, Any] | None = None,
        base_mech_override: dict[str, Any] | None = None,
    ) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        if family_lookup is None:
            family_lookup = family_by_id
        mech = base_mech_override if isinstance(base_mech_override, dict) else base_mech_obj
        worst = 1
        failures: list[dict[str, Any]] = []
        traces: list[dict[str, Any]] = []
        instance_specs: dict[str, Any] = {}
        for entry in pack.get("families", []):
            family_id = entry.get("family_id")
            family = family_lookup.get(family_id)
            if family is None:
                continue
            for theta in entry.get("theta_list", []):
                success, trace, work_delta, failure_kind, inst_hash, instance_spec = eval_instance(
                    epoch_id=epoch_id,
                    family=family,
                    theta=theta,
                    epoch_commit=epoch_commit,
                    base_mech=mech,
                    receipt_hash=sha256_prefixed(canon_bytes({"epoch": epoch_id, "family": family_id})),
                    epoch_key=k_t,
                )
                if record_traces:
                    for event in trace:
                        write_jsonl_line(trace_hold, event)
                        write_jsonl_line(trace_dev, event)
                    traces.extend(trace)
                if record_specs and isinstance(inst_hash, str):
                    if inst_hash in instance_specs and instance_specs[inst_hash] != instance_spec:
                        raise ValueError("instance_spec_mismatch")
                    instance_specs[inst_hash] = instance_spec
                if success == 0:
                    worst = 0
                    if failure_kind:
                        failures.append(
                            {
                                "family_id": family_id,
                                "theta": theta,
                                "inst_hash": inst_hash,
                                "failure_kind": failure_kind,
                                "trace_events": trace,
                                "instance_spec": instance_spec,
                            }
                        )
        return worst, failures, traces, instance_specs

    worst_anchor, anchor_failures, _, anchor_specs = _eval_pack(anchor_pack, record_traces=True, record_specs=True)
    worst_pressure, pressure_failures, _, pressure_specs = _eval_pack(
        pressure_pack, record_traces=True, record_specs=True
    )
    worst_heldout = min(worst_anchor, worst_pressure)
    instance_specs_hold: dict[str, Any] = {}
    for inst_hash, spec in {**anchor_specs, **pressure_specs}.items():
        if inst_hash in instance_specs_hold and instance_specs_hold[inst_hash] != spec:
            raise ValueError("instance_spec_collision")
        instance_specs_hold[inst_hash] = spec

    strict_budget = bool(strict_rsi or strict_integrity)

    def _instance_budget(spec: dict[str, Any]) -> int:
        if not isinstance(spec, dict):
            if strict_budget:
                raise CanonError("eval_budget missing instance_spec")
            return 0
        if "max_env_steps" in spec:
            max_steps = spec.get("max_env_steps")
            if isinstance(max_steps, int):
                return int(max_steps)
            if strict_budget:
                raise CanonError("eval_budget invalid instance_spec.max_env_steps")
        family_id = spec.get("family_id")
        family = family_by_id.get(family_id) if isinstance(family_id, str) else None
        bounds = family.get("resource_bounds") if isinstance(family, dict) else None
        max_steps = bounds.get("max_env_steps_per_instance") if isinstance(bounds, dict) else None
        if isinstance(max_steps, int):
            return int(max_steps)
        if strict_budget:
            raise CanonError("eval_budget missing family resource bounds")
        return 0

    budget_env_steps_anchor = sum(_instance_budget(spec) for spec in anchor_specs.values())
    budget_env_steps_pressure = sum(_instance_budget(spec) for spec in pressure_specs.values())
    budget_env_steps_gate = 0

    # Update pressure schedule deterministically
    thermo = constants["sr"]["thermostat"]
    updated_schedule = update_pressure_schedule(
        pressure_schedule,
        worst_anchor=worst_anchor,
        tau_high=int(thermo["tau_high"]),
        tau_low=int(thermo["tau_low"]),
        n_high=int(thermo["n_high"]),
        n_low=int(thermo["n_low"]),
    )
    updated_schedule["x-meta"] = meta
    write_canon_json(diagnostics_dir / "pressure_schedule_next_v1.json", updated_schedule)

    worstcase_report = {
        "schema": "worstcase_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "x-meta": meta,
        "worst_anchor": worst_anchor,
        "worst_pressure": worst_pressure,
        "worst_heldout": worst_heldout,
    }
    write_canon_json(diagnostics_dir / "worstcase_report_v1.json", worstcase_report)

    success_matrix = {
        "schema": "success_matrix_v1_5r",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "x-meta": meta,
        "base": {
            "worst_anchor": worst_anchor,
            "worst_pressure": worst_pressure,
            "worst_heldout": worst_heldout,
        },
        "candidates": [],
    }
    write_canon_json(out_dir / "success_matrix.json", success_matrix)
    success_candidates: list[dict[str, Any]] = []

    instance_specs_payload = {
        "schema": "instance_specs_v1",
        "schema_version": 1,
        "x-meta": meta,
        "instances": instance_specs_hold,
    }
    write_canon_json(diagnostics_dir / "instance_specs_v1.json", instance_specs_payload)

    translation_report = {
        "schema": "translation_validation_report_v1",
        "schema_version": 1,
        "x-meta": meta,
        "evaluated": False,
    }

    # Failure witnesses + witness ledger (real failures only)
    witness_hashes: list[str] = []
    failures = anchor_failures + pressure_failures
    witness_dir = diagnostics_dir / "witnesses"
    trace_dir = diagnostics_dir / "witness_traces"
    _ensure_dir(witness_dir)
    _ensure_dir(trace_dir)

    def _replay_failure(family: dict[str, Any], theta: dict[str, Any], prefix_events: list[dict[str, Any]]) -> bool:
        instance = instantiate_family(family, theta, epoch_commit, epoch_key=k_t)
        payload = instance.get("payload") or {}
        suite_row = payload.get("suite_row") or {}
        env_kind = suite_row.get("env", "gridworld-v1")
        if not isinstance(env_kind, str):
            env_kind = "gridworld-v1"
        start = suite_row.get("start") or {}
        goal = suite_row.get("goal") or {}
        walls = suite_row.get("walls", [])
        max_steps = int(suite_row.get("max_steps", 1))
        if not isinstance(walls, list):
            return True
        if env_kind == "lineworld-v1":
            try:
                pos = int(start)
                goal_pos = int(goal)
                length = int(suite_row.get("length", 0))
            except Exception:
                return True
            wall_set = {int(w) for w in walls if isinstance(w, int)}
            steps = min(max_steps, len(prefix_events))
            for idx in range(steps):
                action = prefix_events[idx].get("action", {})
                name = action.get("name")
                if name == "NOOP":
                    dx = 0
                else:
                    dir_val = action.get("args", {}).get("dir")
                    if not isinstance(dir_val, int) or dir_val not in {2, 3}:
                        return True
                    dx = -1 if dir_val == 2 else 1
                nxt = pos + dx
                if nxt < 0 or nxt > length or nxt in wall_set:
                    nxt = pos
                pos = nxt
                if pos == goal_pos:
                    return False
            return True
        wall_set = {(int(w.get("x")), int(w.get("y"))) for w in walls if isinstance(w, dict)}
        x, y = int(start.get("x", 0)), int(start.get("y", 0))
        gx, gy = int(goal.get("x", 0)), int(goal.get("y", 0))
        max_x = max([x, gx, *[wx for wx, _ in wall_set]] or [0])
        max_y = max([y, gy, *[wy for _, wy in wall_set]] or [0])
        steps = min(max_steps, len(prefix_events))
        for idx in range(steps):
            action = prefix_events[idx].get("action", {}).get("args", {}).get("dir")
            if not isinstance(action, int):
                return True
            if action not in {0, 1, 2, 3}:
                return True
            dx, dy = {0: (0, 1), 1: (0, -1), 2: (-1, 0), 3: (1, 0)}[action]
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx > max_x or ny > max_y or (nx, ny) in wall_set:
                nx, ny = x, y
            x, y = nx, ny
            if (x, y) == (gx, gy):
                return False
        return True

    for failure in failures:
        family_id = failure.get("family_id")
        family = family_by_id.get(family_id)
        if family is None:
            continue
        theta = failure.get("theta", {})
        inst_hash = failure.get("inst_hash")
        trace_events = failure.get("trace_events", [])
        if not isinstance(inst_hash, str):
            inst_hash = instantiate_family(family, theta, epoch_commit, epoch_key=k_t)["inst_hash"]
        # write per-instance trace
        trace_path = trace_dir / f"trace_{inst_hash.split(':', 1)[1]}.jsonl"
        if trace_path.exists():
            trace_path.unlink()
        for event in trace_events:
            write_jsonl_line(trace_path, event)
        trace_hash = _hash_file(trace_path)

        def _predicate(prefix: list[dict[str, Any]]) -> bool:
            return _replay_failure(family, theta, prefix)

        shrunk, shrink_proof = shrink_trace(trace_events, _predicate, max_gas=64)
        shrink_proof_path = trace_dir / f"shrink_{inst_hash.split(':', 1)[1]}.json"
        write_canon_json(shrink_proof_path, shrink_proof)

        witness = build_failure_witness(
            epoch_id=epoch_id,
            subject="base",
            candidate_id=None,
            family_id=family_id,
            theta=theta,
            inst_hash=inst_hash,
            failure_kind=failure.get("failure_kind") or "GOAL_FAIL",
            trace_hashes=[trace_hash],
            shrink_proof_ref=hash_json(shrink_proof),
        )
        witness_hash = hash_json(witness)
        write_canon_json(witness_dir / f"{witness_hash.split(':', 1)[1]}.json", witness)
        witness_hashes.append(witness_hash)
        bump_short_circuits(1)

    failure_index = {
        "schema": "failure_witness_index_v1",
        "schema_version": 1,
        "witnesses": witness_hashes,
    }
    write_canon_json(diagnostics_dir / "failure_witness_v1.json", failure_index)

    # Macro admission + lifecycle (heldout only)
    trace_events_hold = load_trace_jsonl(str(trace_hold))
    trace_hash = _hash_file(trace_hold)
    macro_active_set_path = state_dir / "current" / "macro_active_set_v1.json"
    macro_ledger_path = state_dir / "current" / "macro_ledger_v1.jsonl"
    macro_active_set = load_canon_json(macro_active_set_path)
    active_macro_ids = list(macro_active_set.get("active_macro_ids", []))
    macro_defs = load_macro_defs(state_dir / "current" / "macros", allowed=active_macro_ids)
    ledger_lines = load_macro_ledger(macro_ledger_path)
    ledger_head = ledger_lines[-1]["line_hash"] if ledger_lines else "sha256:" + "0" * 64

    admission_decisions: list[dict[str, Any]] = []
    macro_admit_candidates: list[dict[str, Any]] = []
    for macro_def in load_macro_proposals(state_dir):
        report = admit_macro(
            macro_def,
            trace_events_hold,
            active_macros=macro_defs,
            instance_specs=instance_specs_hold,
        )
        report["x-meta"] = meta
        admission_decisions.append(report)
        if report.get("decision") == "PASS":
            macro_id = report.get("macro_id")
            if isinstance(macro_id, str) and macro_id not in active_macro_ids:
                candidate_dir = diagnostics_dir / "candidate_macros"
                candidate_dir.mkdir(parents=True, exist_ok=True)
                macro_state_path = candidate_dir / f"{macro_id.split(':', 1)[1]}.json"
                write_canon_json(macro_state_path, macro_def)
                macro_admit_candidates.append(
                    {
                        "macro_id": macro_id,
                        "macro_def_hash": _hash_file(macro_state_path),
                        "report_hash": hash_json(report),
                        "macro_path": macro_state_path,
                        "mdl_gain_bits": int(report.get("mdl_gain_bits", 0)),
                    }
                )

    macro_admission_report = {
        "schema": "macro_admission_report_v1",
        "schema_version": 1,
        "x-meta": meta,
        "decisions": admission_decisions,
    }
    write_canon_json(diagnostics_dir / "macro_admission_report_v1.json", macro_admission_report)
    admitted_ids = [item.get("macro_id") for item in admission_decisions if item.get("decision") == "PASS"]
    admit_receipt = {
        "schema": "macro_admit_receipt_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "report_hash": hash_json(macro_admission_report),
        "admitted_macro_ids": [mid for mid in admitted_ids if isinstance(mid, str)],
    }
    admit_receipt["x-meta"] = meta
    write_canon_json(diagnostics_dir / "macro_admit_receipt_v1.json", admit_receipt)

    # Macro eviction report over rolling heldout window
    epoch_dirs = _list_epoch_dirs(state_dir, out_dir)
    eviction_report = compute_macro_evictions(
        epoch_dirs=epoch_dirs,
        macros_dir=state_dir / "current" / "macros",
        active_macro_ids=active_macro_ids,
    )
    eviction_report["x-meta"] = meta
    macro_deactivate_candidates: list[dict[str, Any]] = []
    evicted_ids = {item.get("macro_id") for item in eviction_report.get("evicted", []) if item.get("macro_id")}
    if evicted_ids:
        reason_map = {
            item.get("macro_id"): item.get("reason_codes", [])
            for item in eviction_report.get("evicted", [])
            if item.get("macro_id")
        }
        mdl_map = {
            item.get("macro_id"): int(item.get("mdl_gain_bits_window", 0))
            for item in eviction_report.get("evicted", [])
            if item.get("macro_id")
        }
        for macro_id in sorted(evicted_ids):
            macro_deactivate_candidates.append(
                {
                    "macro_id": macro_id,
                    "reason_codes": reason_map.get(macro_id, ["DEACTIVATE"]),
                    "mdl_gain_bits_window": mdl_map.get(macro_id, 0),
                    "report_hash": hash_json(eviction_report),
                }
            )
    write_canon_json(diagnostics_dir / "macro_eviction_report_v1.json", eviction_report)

    # Write current active set (no promotion applied yet)
    write_macro_active_set(diagnostics_dir / "macro_active_set_v1.json", active_macro_ids, ledger_head)

    # Macro tokenization + rho reports (heldout) with active macros
    macro_defs = load_macro_defs(state_dir / "current" / "macros", allowed=active_macro_ids)
    token_report = build_macro_tokenization_report(
        epoch_id=epoch_id,
        trace_events=trace_events_hold,
        macro_defs=macro_defs,
        macro_active_set_hash=_hash_file(macro_active_set_path),
        trace_corpus_hashes=[trace_hash],
    )
    token_report["x-meta"] = meta
    write_canon_json(diagnostics_dir / "macro_tokenization_report_heldout_v1.json", token_report)
    rho_report = build_rho_report(epoch_id=epoch_id, tokenization_report=token_report)
    rho_report["x-meta"] = meta
    write_canon_json(diagnostics_dir / "rho_report_v1.json", rho_report)

    def _apply_meta_patch_deltas(workvec: dict[str, Any]) -> dict[str, Any]:
        meta_patch_set_path = state_dir / "current" / "meta_patch_set_v1.json"
        if meta_patch_set_path.exists():
            meta_patch_set = load_canon_json(meta_patch_set_path)
            for patch_id in meta_patch_set.get("active_patch_ids", []):
                patch_path = state_dir / "current" / "meta_patches" / f"{patch_id.split(':', 1)[1]}.json"
                if not patch_path.exists():
                    continue
                patch = load_canon_json(patch_path)
                enable = patch.get("enable") or []
                if isinstance(enable, list):
                    base_bytes = int(workvec.get("bytes_hashed_total", 0))
                    delta_bytes = 0
                    if "HASHCACHE_V1" in enable:
                        delta_bytes += max(1, base_bytes // 10)
                    if "CANON_CACHE_V1" in enable:
                        delta_bytes += max(1, base_bytes // 20)
                    workvec["bytes_hashed_total"] = max(0, base_bytes - delta_bytes)
        return workvec

    # Promotion candidates + selection (dominance)
    workvec_dominance = _apply_meta_patch_deltas(meter.snapshot())
    base_mdl_bits = sum(int(m.get("mdl_gain_bits", 0)) for m in token_report.get("macros", []))
    base_metrics = {
        "worst_anchor": worst_anchor,
        "worst_heldout": worst_heldout,
        "mdl_bits": base_mdl_bits,
        "workvec": workvec_dominance,
    }

    promotion_candidates: list[dict[str, Any]] = []
    candidate_by_id: dict[str, dict[str, Any]] = {}
    invalid_decisions: list[dict[str, Any]] = []

    def _sum_workvecs(items: list[dict[str, Any]], key: str) -> dict[str, int]:
        totals = {
            "verifier_gas_total": 0,
            "env_steps_total": 0,
            "oracle_calls_total": 0,
            "bytes_hashed_total": 0,
            "candidates_fully_evaluated": 0,
            "short_circuits_total": 0,
        }
        for item in items:
            vec = item.get(key)
            if not isinstance(vec, dict):
                continue
            for field in totals:
                totals[field] += int(vec.get(field, 0))
        return totals

    def _strict_workvec_improvement(base_vec: dict[str, Any], new_vec: dict[str, Any]) -> bool:
        eps_work = int(constants["cmeta"]["eps_work"])
        raw_order = constants["cmeta"]["workvec_order"]
        order: list[tuple[str, int]] = []
        for entry in raw_order:
            if isinstance(entry, dict):
                field = entry.get("field")
                direction = entry.get("direction")
                if isinstance(field, str) and direction in {"lower", "higher"}:
                    order.append((field, -1 if direction == "lower" else 1))
            elif isinstance(entry, (list, tuple)) and len(entry) == 2:
                field = entry[0]
                direction = entry[1]
                if isinstance(field, str):
                    order.append((field, int(direction)))
        for field, dir_value in order:
            av = int(new_vec.get(field, 0))
            bv = int(base_vec.get(field, 0))
            if av == bv:
                continue
            if dir_value == -1:
                return av + eps_work <= bv
            return av >= bv + eps_work
        return False

    def _write_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
        candidate_payload = dict(candidate)
        candidate_payload["candidate_id"] = ""
        candidate_id = hash_json(candidate_payload)
        candidate["candidate_id"] = candidate_id
        candidate_dir = diagnostics_dir / "promotion_candidates"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        write_canon_json(candidate_dir / f"{candidate_id.split(':', 1)[1]}.json", candidate)
        promotion_candidates.append(candidate)
        candidate_by_id[candidate_id] = candidate
        return candidate

    # Frontier update candidate
    if admitted_family and next_frontier is not None:
        next_family_objs: list[dict[str, Any]] = []
        candidate_family_by_id = {
            fam.get("family_id"): fam for fam in candidate_family_objs if isinstance(fam.get("family_id"), str)
        }
        for entry in next_frontier.get("families", []):
            fam_id = entry.get("family_id")
            fam_hash = entry.get("family_hash")
            if not isinstance(fam_id, str) or not isinstance(fam_hash, str):
                continue
            fam_obj = candidate_family_by_id.get(fam_id)
            if fam_obj is None:
                fam_path = state_dir / "current" / "families" / f"{fam_hash.split(':', 1)[1]}.json"
                if not fam_path.exists():
                    raise CanonError("missing family file for next_frontier evaluation")
                fam_obj = load_canon_json(fam_path)
            next_family_objs.append(fam_obj)
        candidate_family_by_id = {
            fam.get("family_id"): fam for fam in next_family_objs if isinstance(fam.get("family_id"), str)
        }
        pressure_pack_next = build_pressure_pack(
            frontier_hash=next_frontier["frontier_id"],
            families=next_family_objs,
            n_per_family=n_pressure,
            pressure_level=pressure_level,
        )
        worst_pressure_next, _, _, _ = _eval_pack(
            pressure_pack_next, record_traces=False, record_specs=False, family_lookup=candidate_family_by_id
        )
        worst_heldout_next = min(worst_anchor, worst_pressure_next)

        # Candidate workvec (anchor pack + next pressure pack) for dominance comparison
        candidate_meter = WorkMeter(epoch_id, "sha256:" + "0" * 64)
        set_current_meter(candidate_meter)
        _eval_pack(anchor_pack, record_traces=False, record_specs=False, family_lookup=family_by_id)
        _eval_pack(pressure_pack_next, record_traces=False, record_specs=False, family_lookup=candidate_family_by_id)
        base_short = int(meter.snapshot().get("short_circuits_total", 0))
        candidate_meter.bump("short_circuits_total", base_short)
        set_current_meter(meter)
        workvec_candidate = _apply_meta_patch_deltas(candidate_meter.snapshot())
        base_ids = {fam.get("family_id") for fam in frontier.get("families", [])}
        next_ids = {fam.get("family_id") for fam in next_frontier.get("families", [])}
        frontier_churn = len((base_ids - next_ids) | (next_ids - base_ids))
        frontier_candidate = _write_candidate(
            {
                "schema": "promotion_candidate_v1",
                "schema_version": 1,
                "promotion_type": "frontier_update",
                "base_state_hashes": base_state_hashes,
                "delta_artifacts": [
                    {"name": "frontier_v1_next.json", "hash": _hash_file(diagnostics_dir / "frontier_v1_next.json")},
                    {"name": "frontier_update_report_v1.json", "hash": _hash_file(diagnostics_dir / "frontier_update_report_v1.json")},
                ],
                "claimed_metrics": {
                    "worst_anchor": worst_anchor,
                    "worst_heldout": worst_heldout_next,
                    "mdl_bits": base_mdl_bits,
                    "workvec": workvec_candidate,
                },
                "evidence_refs": [_hash_file(diagnostics_dir / "frontier_update_report_v1.json")],
                "meta": {
                    "new_symbols": 1,
                    "active_macro_count": len(active_macro_ids),
                    "frontier_churn": frontier_churn,
                    "hash": "",
                },
            }
        )
        success_candidates.append(
            {
                "candidate_id": frontier_candidate["candidate_id"],
                "promotion_type": "frontier_update",
                "worst_anchor": worst_anchor,
                "worst_pressure": worst_pressure_next,
                "worst_heldout": worst_heldout_next,
            }
        )

    # Pressure schedule update candidate
    if updated_schedule.get("p_t") != pressure_schedule.get("p_t"):
        pressure_pack_next = build_pressure_pack(
            frontier_hash=frontier_hash,
            families=family_objs,
            n_per_family=n_pressure,
            pressure_level=int(updated_schedule.get("p_t", pressure_level)),
        )
        worst_pressure_next, _, _, _ = _eval_pack(
            pressure_pack_next, record_traces=False, record_specs=False, family_lookup=family_by_id
        )
        worst_heldout_next = min(worst_anchor, worst_pressure_next)
        pressure_candidate = _write_candidate(
            {
                "schema": "promotion_candidate_v1",
                "schema_version": 1,
                "promotion_type": "pressure_update",
                "base_state_hashes": base_state_hashes,
                "delta_artifacts": [
                    {"name": "pressure_schedule_next_v1.json", "hash": _hash_file(diagnostics_dir / "pressure_schedule_next_v1.json")},
                ],
                "claimed_metrics": {
                    "worst_anchor": worst_anchor,
                    "worst_heldout": worst_heldout_next,
                    "mdl_bits": base_mdl_bits,
                    "workvec": workvec_dominance,
                },
                "evidence_refs": [_hash_file(diagnostics_dir / "pressure_schedule_next_v1.json")],
                "meta": {
                    "new_symbols": 0,
                    "active_macro_count": len(active_macro_ids),
                    "frontier_churn": 0,
                    "hash": "",
                },
            }
        )
        success_candidates.append(
            {
                "candidate_id": pressure_candidate["candidate_id"],
                "promotion_type": "pressure_update",
                "worst_anchor": worst_anchor,
                "worst_pressure": worst_pressure_next,
                "worst_heldout": worst_heldout_next,
            }
        )

    # Macro admission candidates
    for candidate in macro_admit_candidates:
        new_mdl_bits = base_mdl_bits + int(candidate.get("mdl_gain_bits", 0))
        _write_candidate(
            {
                "schema": "promotion_candidate_v1",
                "schema_version": 1,
                "promotion_type": "macro_admit",
                "base_state_hashes": base_state_hashes,
                "delta_artifacts": [
                    {"name": "macro_def", "hash": candidate["macro_def_hash"]},
                    {"name": "macro_admission_report_v1.json", "hash": candidate["report_hash"]},
                ],
                "claimed_metrics": {
                    "worst_anchor": worst_anchor,
                    "worst_heldout": worst_heldout,
                    "mdl_bits": new_mdl_bits,
                    "workvec": workvec_dominance,
                },
                "evidence_refs": [candidate["report_hash"]],
                "meta": {
                    "new_symbols": 2,
                    "active_macro_count": len(active_macro_ids) + 1,
                    "frontier_churn": 0,
                    "hash": "",
                    "macro_id": candidate.get("macro_id"),
                },
            }
        )

    # Macro deactivation candidates
    for candidate in macro_deactivate_candidates:
        improvement_bits = max(0, -int(candidate.get("mdl_gain_bits_window", 0)))
        new_mdl_bits = base_mdl_bits + improvement_bits
        _write_candidate(
            {
                "schema": "promotion_candidate_v1",
                "schema_version": 1,
                "promotion_type": "macro_deactivate",
                "base_state_hashes": base_state_hashes,
                "delta_artifacts": [
                    {"name": "macro_id", "hash": candidate.get("macro_id")},
                    {"name": "macro_eviction_report_v1.json", "hash": candidate.get("report_hash")},
                ],
                "claimed_metrics": {
                    "worst_anchor": worst_anchor,
                    "worst_heldout": worst_heldout,
                    "mdl_bits": new_mdl_bits,
                    "workvec": workvec_dominance,
                },
                "evidence_refs": [candidate.get("report_hash")],
                "meta": {
                    "new_symbols": 0,
                    "active_macro_count": max(0, len(active_macro_ids) - 1),
                    "frontier_churn": 0,
                    "hash": "",
                    "macro_id": candidate.get("macro_id"),
                    "reason_codes": candidate.get("reason_codes", ["DEACTIVATE"]),
                },
            }
        )

    # Mechanism patch candidates
    for patch in load_mech_patch_proposals(state_dir):
        patch_id = patch.get("patch_id") or hash_json(patch)
        if not isinstance(patch_id, str):
            invalid_decisions.append(
                {
                    "candidate_id": "mech_patch",
                    "promotion_type": "mech_patch",
                    "decision": "FAIL",
                    "reason": "missing_patch_id",
                }
            )
            continue
        base_state_hash = patch.get("base_state_hash")
        if current_state_head_hash and base_state_hash != current_state_head_hash:
            invalid_decisions.append(
                {
                    "candidate_id": patch_id,
                    "promotion_type": "mech_patch",
                    "decision": "FAIL",
                    "reason": "base_state_hash_mismatch",
                }
            )
            continue
        try:
            candidate_mech = _apply_mech_patch(base_mech_obj, patch)
        except CanonError as exc:
            invalid_decisions.append(
                {
                    "candidate_id": patch_id,
                    "promotion_type": "mech_patch",
                    "decision": "FAIL",
                    "reason": str(exc),
                }
            )
            continue

        worst_anchor_next, _, _, _ = _eval_pack(
            anchor_pack, record_traces=False, record_specs=False, base_mech_override=candidate_mech
        )
        worst_pressure_next, _, _, _ = _eval_pack(
            pressure_pack, record_traces=False, record_specs=False, base_mech_override=candidate_mech
        )
        worst_heldout_next = min(worst_anchor_next, worst_pressure_next)

        candidate_meter = WorkMeter(epoch_id, "sha256:" + "0" * 64)
        set_current_meter(candidate_meter)
        _eval_pack(anchor_pack, record_traces=False, record_specs=False, base_mech_override=candidate_mech)
        _eval_pack(pressure_pack, record_traces=False, record_specs=False, base_mech_override=candidate_mech)
        base_short = int(meter.snapshot().get("short_circuits_total", 0))
        candidate_meter.bump("short_circuits_total", base_short)
        set_current_meter(meter)
        workvec_candidate = candidate_meter.snapshot()

        candidate_dir = diagnostics_dir / "candidate_mech_patches"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        candidate_patch_path = candidate_dir / f"{patch_id.split(':', 1)[1]}.json"
        write_canon_json(candidate_patch_path, patch)

        _write_candidate(
            {
                "schema": "promotion_candidate_v1",
                "schema_version": 1,
                "promotion_type": "mech_patch",
                "base_state_hashes": base_state_hashes,
                "delta_artifacts": [{"name": "mech_patch", "hash": _hash_file(candidate_patch_path)}],
                "claimed_metrics": {
                    "worst_anchor": worst_anchor_next,
                    "worst_heldout": worst_heldout_next,
                    "mdl_bits": base_mdl_bits,
                    "workvec": workvec_candidate,
                },
                "evidence_refs": [_hash_file(candidate_patch_path)],
                "meta": {
                    "new_symbols": 2,
                    "active_macro_count": len(active_macro_ids),
                    "frontier_churn": 0,
                    "hash": "",
                    "patch_id": patch_id,
                },
            }
        )

    # Meta-patch proposals (translation validated)
    meta_patch_proposals = load_meta_patch_proposals(state_dir)
    meta_patch_decisions: list[dict[str, Any]] = []
    meta_patch_candidates: list[tuple[int, str, dict[str, Any], dict[str, Any]]] = []
    benchmark_path = state_dir / "current" / "meta_benchmark_pack_v1.json"
    benchmark_pack = load_benchmark_pack(benchmark_path) if benchmark_path.exists() else None
    benchmark_hash = _hash_file(benchmark_path) if benchmark_path.exists() else None
    meta_patch_set_hash = _hash_file(state_dir / "current" / "meta_patch_set_v1.json")

    for proposal in meta_patch_proposals:
        patch_id = proposal.get("patch_id")
        if not isinstance(patch_id, str):
            continue
        reason_codes: list[str] = []
        if proposal.get("base_meta_patch_set_hash") != meta_patch_set_hash:
            reason_codes.append("META_PATCH_BASE_SET_MISMATCH")
        if benchmark_pack is None or benchmark_hash is None:
            reason_codes.append("BENCHMARK_PACK_MISSING")
        elif proposal.get("benchmark_pack_hash") != benchmark_hash:
            reason_codes.append("BENCHMARK_PACK_HASH_MISMATCH")
        if proposal.get("equiv_relation_id") != constants.get("cmeta", {}).get("meta_equiv_id"):
            reason_codes.append("EQUIV_RELATION_MISMATCH")
        if reason_codes:
            meta_patch_decisions.append(
                {"patch_id": patch_id, "decision": "FAIL", "reason_codes": reason_codes}
            )
            continue
        try:
            cert = translate_validate(
                {
                    **proposal,
                    "epoch_id": epoch_id,
                },
                benchmark_pack,
            )
        except Exception as exc:  # noqa: BLE001
            meta_patch_decisions.append(
                {
                    "patch_id": patch_id,
                    "decision": "FAIL",
                    "reason_codes": ["TRANSLATION_VALIDATE_ERROR"],
                }
            )
            continue

        cert["x-meta"] = meta
        cert_dir = diagnostics_dir / "meta_patch_certs"
        cert_dir.mkdir(parents=True, exist_ok=True)
        cert_path = cert_dir / f"{patch_id.split(':', 1)[1]}.translation_cert_v1.json"
        write_canon_json(cert_path, cert)
        overall = cert.get("overall", {})
        if not (overall.get("equiv_ok") and overall.get("dominance_ok") and overall.get("strict_improve_ok")):
            fail_reasons: list[str] = []
            if not overall.get("equiv_ok"):
                fail_reasons.append("TRANSLATION_EQUIV_FAIL")
            if not overall.get("dominance_ok"):
                fail_reasons.append("TRANSLATION_DOMINANCE_FAIL")
            if not overall.get("strict_improve_ok"):
                fail_reasons.append("TRANSLATION_NO_IMPROVE")
            meta_patch_decisions.append(
                {
                    "patch_id": patch_id,
                    "decision": "FAIL",
                    "reason_codes": fail_reasons or ["TRANSLATION_CERT_REJECT"],
                }
            )
            continue

        cases = cert.get("cases", [])
        if not isinstance(cases, list):
            cases = []
        base_workvec = _sum_workvecs(cases, "workvec_base")
        patch_workvec = _sum_workvecs(cases, "workvec_new")
        improvement = int(base_workvec.get("bytes_hashed_total", 0)) - int(
            patch_workvec.get("bytes_hashed_total", 0)
        )
        meta_patch_candidates.append((improvement, patch_id, proposal, cert))
        meta_patch_decisions.append(
            {"patch_id": patch_id, "decision": "PASS", "reason_codes": []}
        )

    if meta_patch_decisions:
        meta_patch_report = {
            "schema": "meta_patch_admission_report_v1",
            "schema_version": 1,
            "x-meta": meta,
            "decisions": meta_patch_decisions,
        }
        write_canon_json(diagnostics_dir / "meta_patch_admission_report_v1.json", meta_patch_report)
        admitted_ids = [
            d.get("patch_id")
            for d in meta_patch_decisions
            if d.get("decision") == "PASS" and isinstance(d.get("patch_id"), str)
        ]
        admit_receipt = {
            "schema": "meta_patch_admit_receipt_v1",
            "schema_version": 1,
            "epoch_id": epoch_id,
            "admitted_patch_ids": admitted_ids,
            "report_hash": hash_json(meta_patch_report),
        }
        admit_receipt["x-meta"] = meta
        write_canon_json(diagnostics_dir / "meta_patch_admit_receipt_v1.json", admit_receipt)

    if meta_patch_candidates:
        meta_patch_candidates.sort(key=lambda item: (-item[0], item[1]))
        improvement, patch_id, proposal, cert = meta_patch_candidates[0]
        candidate_dir = diagnostics_dir / "candidate_meta_patches"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        candidate_patch_path = candidate_dir / f"{patch_id.split(':', 1)[1]}.json"
        write_canon_json(candidate_patch_path, proposal)
        candidate_cert_path = candidate_dir / f"{patch_id.split(':', 1)[1]}.translation_cert_v1.json"
        write_canon_json(candidate_cert_path, cert)
        # also emit translation_cert_v1.json for the selected patch
        write_canon_json(diagnostics_dir / "translation_cert_v1.json", cert)

        cases = cert.get("cases", [])
        if not isinstance(cases, list):
            cases = []
        base_workvec = _sum_workvecs(cases, "workvec_base")
        patch_workvec = _sum_workvecs(cases, "workvec_new")
        _write_candidate(
            {
                "schema": "promotion_candidate_v1",
                "schema_version": 1,
                "promotion_type": "meta_patch",
                "base_state_hashes": base_state_hashes,
                "delta_artifacts": [
                    {"name": "meta_patch_proposal_v1.json", "hash": _hash_file(candidate_patch_path)},
                    {"name": "translation_cert_v1.json", "hash": _hash_file(candidate_cert_path)},
                ],
                "claimed_metrics": {
                    "worst_anchor": worst_anchor,
                    "worst_heldout": worst_heldout,
                    "mdl_bits": base_mdl_bits,
                    "workvec": patch_workvec,
                },
                "base_metrics": {
                    "worst_anchor": worst_anchor,
                    "worst_heldout": worst_heldout,
                    "mdl_bits": base_mdl_bits,
                    "workvec": base_workvec,
                },
                "evidence_refs": [_hash_file(candidate_cert_path)],
                "meta": {
                    "new_symbols": 0,
                    "active_macro_count": len(active_macro_ids),
                    "frontier_churn": 0,
                    "hash": "",
                    "patch_id": patch_id,
                    "translation_cert_path": str(candidate_cert_path.relative_to(diagnostics_dir)),
                },
            }
        )

    if success_candidates:
        success_matrix["candidates"] = success_candidates
        write_canon_json(out_dir / "success_matrix.json", success_matrix)

    # Evaluate dominance
    candidate_decisions = {
        "schema": "candidate_decisions_v1_5r",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "x-meta": meta,
        "decisions": [],
    }
    passing: list[dict[str, Any]] = []
    for candidate in promotion_candidates:
        new_metrics = candidate.get("claimed_metrics", {})
        base_for_candidate = candidate.get("base_metrics") or base_metrics
        bump_verifier_gas(1)
        ok, reason = dominance_decision(base_for_candidate, new_metrics)
        candidate["meta"]["hash"] = candidate["candidate_id"]
        candidate_decisions["decisions"].append(
            {
                "candidate_id": candidate["candidate_id"],
                "promotion_type": candidate.get("promotion_type"),
                "decision": "PASS" if ok else "FAIL",
                "reason": reason,
            }
        )
        if ok:
            passing.append(candidate)

    selected_candidate_id = None
    if passing:
        passing.sort(key=lambda cand: tiebreak_key(cand.get("meta", {})))
        selected_candidate_id = passing[0]["candidate_id"]

    # add invalid decisions
    if invalid_decisions:
        candidate_decisions["decisions"].extend(invalid_decisions)

    selected_candidate = candidate_by_id.get(selected_candidate_id) if selected_candidate_id else None
    selected_reason = None
    if selected_candidate_id:
        for item in candidate_decisions["decisions"]:
            if item.get("candidate_id") == selected_candidate_id:
                selected_reason = item.get("reason")
                break
    dominance_witness = {
        "schema": "dominance_witness_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "base_metrics": base_metrics,
        "selected_candidate_id": selected_candidate_id,
        "selected_reason": selected_reason,
        "candidate_metrics": selected_candidate.get("claimed_metrics") if selected_candidate else None,
        "decisions": candidate_decisions["decisions"],
    }
    write_canon_json(diagnostics_dir / "dominance_witness_v1.json", dominance_witness)

    # Meta-core verify selected promotion bundle (fail-closed)
    if selected_candidate:
        bundle_dir, _manifest = _write_promotion_bundle(diagnostics_dir=diagnostics_dir, candidate=selected_candidate, meta=meta)
        receipt_path = bundle_dir / "promotion_receipt_v1.json"
        bump_verifier_gas(1)
        subprocess.run(
            [
                sys.executable,
                str(_meta_core_root() / "kernel" / "verify_promotion_bundle.py"),
                "--bundle_dir",
                str(bundle_dir),
                "--meta_core_root",
                str(_meta_core_root()),
                "--out",
                str(receipt_path),
            ],
            check=True,
        )
        receipt = load_canon_json(receipt_path)
        if receipt.get("verdict") != "VALID":
            candidate_decisions["decisions"].append(
                {
                    "candidate_id": selected_candidate_id,
                    "promotion_type": selected_candidate.get("promotion_type"),
                    "decision": "FAIL",
                    "reason": "meta_core_invalid",
                }
            )
            selected_candidate_id = None
            selected_candidate = None
            selected_reason = "meta_core_invalid"

    selection = {
        "schema": "selection_v1_5r",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "x-meta": meta,
        "selected_candidate_id": selected_candidate_id,
    }
    write_canon_json(out_dir / "selection.json", selection)
    write_canon_json(out_dir / "candidate_decisions.json", candidate_decisions)

    if selected_candidate_id:
        for item in candidate_decisions["decisions"]:
            if item.get("candidate_id") == selected_candidate_id:
                selected_reason = item.get("reason")
                break

    dominance_witness = {
        "schema": "dominance_witness_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "base_metrics": base_metrics,
        "selected_candidate_id": selected_candidate_id,
        "selected_reason": selected_reason,
        "candidate_metrics": selected_candidate.get("claimed_metrics") if selected_candidate else None,
        "decisions": candidate_decisions["decisions"],
    }
    write_canon_json(diagnostics_dir / "dominance_witness_v1.json", dominance_witness)

    # Apply selected promotion (atomic pointers)
    frontier_hash_after = frontier_hash
    if selected_candidate:
        promotion_type = selected_candidate.get("promotion_type")
        if promotion_type == "frontier_update" and next_frontier is not None:
            prev_hash_payload = {
                "schema": "frontier_prev_hash_v1",
                "schema_version": 1,
                "frontier_hash": frontier_hash,
            }
            write_canon_json(state_dir / "current" / "frontier_prev_hash_v1.json", prev_hash_payload)
            # persist admitted family then frontier update
            if admitted_family:
                admitted_hash = hash_json(admitted_family)
                families_dir = state_dir / "current" / "families"
                families_dir.mkdir(parents=True, exist_ok=True)
                candidate_path = diagnostics_dir / "candidate_families" / f"{admitted_hash.split(':', 1)[1]}.json"
                if candidate_path.exists():
                    write_canon_json(families_dir / f"{admitted_hash.split(':', 1)[1]}.json", admitted_family)
                    registry[admitted_family["family_id"]] = admitted_hash
                    write_canon_json(registry_path, registry)
            write_canon_json(state_dir / "current" / "frontier_v1.json", next_frontier)
            frontier_hash_after = hash_json(next_frontier)
        elif promotion_type == "macro_admit":
            macro_id = selected_candidate.get("meta", {}).get("macro_id")
            if isinstance(macro_id, str):
                macro_path = diagnostics_dir / "candidate_macros" / f"{macro_id.split(':', 1)[1]}.json"
                if macro_path.exists():
                    macro_state_path = state_dir / "current" / "macros" / f"{macro_id.split(':', 1)[1]}.json"
                    macro_state_path.parent.mkdir(parents=True, exist_ok=True)
                    write_canon_json(macro_state_path, load_canon_json(macro_path))
                    evidence_refs = list(selected_candidate.get("evidence_refs") or [])
                    entry = update_macro_ledger(
                        macro_ledger_path,
                        event="ADMIT",
                        macro_id=macro_id,
                        ref_hash=_hash_file(macro_state_path),
                        epoch_id=epoch_id,
                        reason_codes=["ADMIT"],
                        evidence_refs=evidence_refs[:1],
                    )
                    ledger_head = entry["line_hash"]
                    updated_ids = list(active_macro_ids) + [macro_id]
                    write_macro_active_set(macro_active_set_path, updated_ids, ledger_head)
        elif promotion_type == "macro_deactivate":
            macro_id = selected_candidate.get("meta", {}).get("macro_id")
            if isinstance(macro_id, str):
                evidence_refs = list(selected_candidate.get("evidence_refs") or [])
                entry = update_macro_ledger(
                    macro_ledger_path,
                    event="DEACTIVATE",
                    macro_id=macro_id,
                    ref_hash=macro_id,
                    epoch_id=epoch_id,
                    reason_codes=selected_candidate.get("meta", {}).get("reason_codes", ["DEACTIVATE"]),
                    evidence_refs=evidence_refs[:1],
                )
                ledger_head = entry["line_hash"]
                updated_ids = [mid for mid in active_macro_ids if mid != macro_id]
                write_macro_active_set(macro_active_set_path, updated_ids, ledger_head)
        elif promotion_type == "pressure_update":
            write_canon_json(state_dir / "current" / "pressure_schedule_v1.json", updated_schedule)
        elif promotion_type == "meta_patch":
            patch_id = selected_candidate.get("meta", {}).get("patch_id")
            if isinstance(patch_id, str):
                patch_path = diagnostics_dir / "candidate_meta_patches" / f"{patch_id.split(':', 1)[1]}.json"
                if patch_path.exists():
                    patches_dir = state_dir / "current" / "meta_patches"
                    patches_dir.mkdir(parents=True, exist_ok=True)
                    state_patch_path = patches_dir / f"{patch_id.split(':', 1)[1]}.json"
                    write_canon_json(state_patch_path, load_canon_json(patch_path))
                    meta_patch_set_path = state_dir / "current" / "meta_patch_set_v1.json"
                    meta_patch_set = load_canon_json(meta_patch_set_path)
                    active_ids = list(meta_patch_set.get("active_patch_ids", []))
                    if patch_id not in active_ids:
                        active_ids.append(patch_id)
                    meta_patch_set["active_patch_ids"] = sorted(set(active_ids))
                    write_canon_json(meta_patch_set_path, meta_patch_set)
                    ledger_path = state_dir / "current" / "meta_patch_ledger_v1.jsonl"
                    if not ledger_path.exists():
                        ledger_path.write_text("", encoding="utf-8")
                    ledger_entries = _load_jsonl_payloads(ledger_path)
                    prev_hash = ledger_entries[-1].get("line_hash") if ledger_entries else "sha256:" + "0" * 64
                    ledger_event = {
                        "schema": "meta_patch_ledger_event_v1",
                        "schema_version": 1,
                        "epoch_id": epoch_id,
                        "event": "ADMIT",
                        "patch_id": patch_id,
                        "ref_hash": _hash_file(state_patch_path),
                        "prev_ledger_hash": prev_hash,
                    }
                    ledger_event["line_hash"] = hash_json(
                        {k: v for k, v in ledger_event.items() if k != "line_hash"}
                    )
                    ledger_event["x-meta"] = meta
                    write_jsonl_line(ledger_path, ledger_event)
        elif promotion_type == "mech_patch":
            patch_id = selected_candidate.get("meta", {}).get("patch_id")
            if isinstance(patch_id, str):
                patch_path = diagnostics_dir / "candidate_mech_patches" / f"{patch_id.split(':', 1)[1]}.json"
                if patch_path.exists():
                    patches_dir = state_dir / "current" / "mech_patches"
                    patches_dir.mkdir(parents=True, exist_ok=True)
                    state_patch_path = patches_dir / f"{patch_id.split(':', 1)[1]}.json"
                    patch_payload = load_canon_json(patch_path)
                    write_canon_json(state_patch_path, patch_payload)
                    base_mech_payload = load_canon_json(state_dir / "current" / "base_mech.json")
                    updated_mech = _apply_mech_patch(base_mech_payload, patch_payload)
                    write_canon_json(state_dir / "current" / "base_mech.json", updated_mech)

    effective_frontier = next_frontier if selected_candidate and selected_candidate.get("promotion_type") == "frontier_update" else frontier
    epoch_summary = {
        "schema": "epoch_summary_v1_5r",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "x-meta": meta,
        "families": [fam.get("family_id") for fam in effective_frontier.get("families", [])],
    }
    write_canon_json(out_dir / "epoch_summary.json", epoch_summary)

    # State ledger (single head hash chain)
    state_ledger_path = state_dir / "current" / "state_ledger_v1.jsonl"
    if not state_ledger_path.exists():
        state_ledger_path.write_text("", encoding="utf-8")
    ledger_lines: list[dict[str, Any]] = []
    for raw in state_ledger_path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            payload = loads(raw)
            if raw.strip() != canon_bytes(payload).decode("utf-8"):
                raise CanonError("non-canonical state ledger line")
            if not isinstance(payload, dict):
                raise CanonError("state ledger entry must be object")
            ledger_lines.append(payload)
    prev_hash = ledger_lines[-1].get("line_hash") if ledger_lines else "sha256:" + "0" * 64
    pointer_hashes = {
        "frontier_hash": _hash_file(state_dir / "current" / "frontier_v1.json"),
        "macro_active_set_hash": _hash_file(state_dir / "current" / "macro_active_set_v1.json"),
        "pressure_schedule_hash": _hash_file(state_dir / "current" / "pressure_schedule_v1.json"),
        "meta_patch_set_hash": _hash_file(state_dir / "current" / "meta_patch_set_v1.json"),
    }
    state_entry = {
        "schema": "state_ledger_event_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "selected_candidate_id": selected_candidate_id,
        "pointer_hashes": pointer_hashes,
        "prev_ledger_hash": prev_hash,
    }
    if selected_candidate and selected_candidate.get("promotion_type") == "frontier_update":
        frontier_report_path = diagnostics_dir / "frontier_update_report_v1.json"
        if not frontier_report_path.exists():
            raise CanonError("frontier_update_report_v1.json missing for frontier activation event")
        frontier_report = load_canon_json(frontier_report_path)
        inserted_family_id = frontier_report.get("admitted_family_id")
        if not isinstance(inserted_family_id, str):
            raise CanonError("frontier_update_report_v1.json missing admitted_family_id")
        state_entry["frontier_event"] = {
            "event_type": "FRONTIER_ACTIVATE_V1",
            "schema_version": 1,
            "prev_frontier_hash": frontier_hash,
            "new_frontier_hash": frontier_hash_after,
            "inserted_family_id": inserted_family_id,
            "compression_detail_hash": _hash_file(frontier_report_path),
            "reason_code": "FRONTIER_INSERTION",
        }
    if selected_candidate and selected_candidate.get("promotion_type") == "mech_patch":
        patch_id = selected_candidate.get("meta", {}).get("patch_id")
        if isinstance(patch_id, str):
            patch_path = diagnostics_dir / "candidate_mech_patches" / f"{patch_id.split(':', 1)[1]}.json"
            if not patch_path.exists():
                raise CanonError("candidate_mech_patches missing for mech patch event")
            patch_payload = load_canon_json(patch_path)
            base_state_hash = patch_payload.get("base_state_hash")
            state_entry["mech_patch_event"] = {
                "event_type": "MECH_PATCH_ACTIVATE_V1",
                "schema_version": 1,
                "patch_id": patch_id,
                "patch_hash": _hash_file(patch_path),
                "base_state_hash": base_state_hash,
                "reason_code": "MECH_PATCH",
            }
    if selected_candidate and selected_candidate.get("promotion_type") == "meta_patch":
        patch_id = selected_candidate.get("meta", {}).get("patch_id")
        if isinstance(patch_id, str):
            patch_path = diagnostics_dir / "candidate_meta_patches" / f"{patch_id.split(':', 1)[1]}.json"
            if not patch_path.exists():
                raise CanonError("candidate_meta_patches missing for meta patch event")
            state_entry["meta_patch_event"] = {
                "event_type": "META_PATCH_ACTIVATE_V1",
                "schema_version": 1,
                "patch_id": patch_id,
                "patch_hash": _hash_file(patch_path),
                "reason_code": "META_PATCH",
            }
    line_hash = sha256_prefixed(canon_bytes(state_entry))
    state_entry["line_hash"] = line_hash
    write_jsonl_line(state_ledger_path, state_entry)
    state_head_payload = {
        "schema": "state_ledger_head_v1",
        "schema_version": 1,
        "ledger_head_hash": line_hash,
        "line_count": len(ledger_lines) + 1,
    }
    write_canon_json(state_dir / "current" / "state_ledger_head_v1.json", state_head_payload)
    write_canon_json(diagnostics_dir / "state_ledger_head_v1.json", state_head_payload)

    # Recompute macro tokenization + rho reports after promotion applied
    macro_active_set_post = load_canon_json(macro_active_set_path)
    active_macro_ids_post = list(macro_active_set_post.get("active_macro_ids", []))
    macro_defs_post = load_macro_defs(state_dir / "current" / "macros", allowed=active_macro_ids_post)
    token_report_post = build_macro_tokenization_report(
        epoch_id=epoch_id,
        trace_events=trace_events_hold,
        macro_defs=macro_defs_post,
        macro_active_set_hash=_hash_file(macro_active_set_path),
        trace_corpus_hashes=[trace_hash],
    )
    token_report_post["x-meta"] = meta
    write_canon_json(diagnostics_dir / "macro_tokenization_report_heldout_v1.json", token_report_post)
    rho_report_post = build_rho_report(epoch_id=epoch_id, tokenization_report=token_report_post)
    rho_report_post["x-meta"] = meta
    write_canon_json(diagnostics_dir / "rho_report_v1.json", rho_report_post)

    # Write translation validation report (placeholder until meta-patches run)
    write_canon_json(diagnostics_dir / "translation_validation_report_v1.json", translation_report)

    # Final work meter snapshot (after selection/receipts)
    work_meter = _apply_meta_patch_deltas(meter.snapshot())
    work_meter["x-meta"] = meta
    write_canon_json(out_dir / "work_meter_v1.json", work_meter)

    eval_budget_report = {
        "schema": "eval_budget_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "anchor_pack_hash": _hash_file(diagnostics_dir / "anchor_pack_v1.json"),
        "pressure_pack_hash": _hash_file(diagnostics_dir / "pressure_pack_v1.json"),
        "counts": {
            "n_anchor_instances": len(anchor_specs),
            "n_pressure_instances": len(pressure_specs),
            "n_gate_instances": 0,
        },
        "budgets": {
            "budget_env_steps_anchor": int(budget_env_steps_anchor),
            "budget_env_steps_pressure": int(budget_env_steps_pressure),
            "budget_env_steps_gate": int(budget_env_steps_gate),
            "budget_env_steps_total": int(budget_env_steps_anchor + budget_env_steps_pressure + budget_env_steps_gate),
        },
        "realized": {"env_steps_total": int(work_meter.get("env_steps_total", 0))},
        "evidence": {
            "work_meter_hash": _hash_file(out_dir / "work_meter_v1.json"),
            "worstcase_report_hash": _hash_file(diagnostics_dir / "worstcase_report_v1.json"),
            "selection_hash": _hash_file(out_dir / "selection.json"),
            "state_ledger_head_hash": _hash_file(diagnostics_dir / "state_ledger_head_v1.json"),
        },
    }
    eval_budget_report["x-meta"] = meta
    write_canon_json(diagnostics_dir / "eval_budget_report_v1.json", eval_budget_report)

    # Barrier record (per-epoch)
    frontier_changed = bool(
        selected_candidate and selected_candidate.get("promotion_type") == "frontier_update"
    )
    frontier_hash_before = frontier_hash
    prev_hash_path = state_dir / "current" / "frontier_prev_hash_v1.json"
    if prev_hash_path.exists():
        prev_payload = load_canon_json(prev_hash_path)
        prev_frontier_hash = prev_payload.get("frontier_hash")
        if isinstance(prev_frontier_hash, str):
            frontier_hash_before = prev_frontier_hash
        frontier_changed = True
        prev_hash_path.unlink()
    recovered = success_matrix["base"].get("worst_anchor") == 1 and success_matrix["base"].get("worst_heldout") == 1

    prev_record = None
    if len(epoch_dirs) > 1:
        prev_record = _load_barrier_record(epoch_dirs[-2])

    start_epoch_id, recovery_epoch_id, workvec_since_last, recovery_state = advance_barrier_state(
        prev_record=prev_record,
        frontier_changed=frontier_changed,
        recovered=recovered,
        epoch_id=epoch_id,
        workvec_epoch=work_meter,
    )

    window_state = {
        "start_epoch_id": start_epoch_id,
        "recovery_epoch_id": recovery_epoch_id,
        "recovery_state": recovery_state,
        "frontier_hash_before": frontier_hash_before,
        "frontier_hash_after": frontier_hash_after,
    }
    window_state["window_id"] = sha256_prefixed(canon_bytes(window_state))

    barrier_scalar_value = barrier_scalar(workvec_since_last) if recovery_state == "RECOVERED" else 0
    barrier_record = build_barrier_record(
        frontier_hash_before=frontier_hash_before,
        frontier_hash_after=frontier_hash_after,
        start_epoch_id=start_epoch_id,
        recovery_epoch_id=recovery_epoch_id,
        workvec_epoch=work_meter,
        workvec_since_last_insertion=workvec_since_last,
        recovery_state=recovery_state,
        barrier_scalar_rule_id="SCALAR=env_steps_total_v1",
        barrier_scalar_value=barrier_scalar_value,
        barrier_window_state=window_state,
        proofs=[_hash_file(out_dir / "work_meter_v1.json"), _hash_file(out_dir / "selection.json")],
    )
    barrier_record["x-meta"] = meta
    write_canon_json(out_dir / "barrier_record_v1.json", barrier_record)
    write_canon_json(diagnostics_dir / "barrier_record_v1.json", barrier_record)

    # RSI tracker (deterministic, fail-closed in strict mode)
    rsi_state_path = state_dir / "current" / "rsi_tracker_state_v1.json"
    prior_rsi_state = load_canon_json(rsi_state_path) if rsi_state_path.exists() else None
    rsi_epoch_artifacts = {
        "epoch_id": epoch_id,
        "meta": meta,
        "anchor_pack_hash": _hash_file(diagnostics_dir / "anchor_pack_v1.json"),
        "worstcase_report": load_canon_json(diagnostics_dir / "worstcase_report_v1.json"),
        "worstcase_report_hash": _hash_file(diagnostics_dir / "worstcase_report_v1.json"),
        "selection": load_canon_json(out_dir / "selection.json"),
        "selection_hash": _hash_file(out_dir / "selection.json"),
        "work_meter": load_canon_json(out_dir / "work_meter_v1.json"),
        "work_meter_hash": _hash_file(out_dir / "work_meter_v1.json"),
        "rho_report": load_canon_json(diagnostics_dir / "rho_report_v1.json"),
        "rho_report_hash": _hash_file(diagnostics_dir / "rho_report_v1.json"),
        "state_ledger_head": load_canon_json(diagnostics_dir / "state_ledger_head_v1.json"),
        "state_ledger_head_hash": _hash_file(diagnostics_dir / "state_ledger_head_v1.json"),
        "state_ledger_event": state_entry,
    }
    rsi_result = update_rsi_tracker(
        constants=constants,
        epoch_artifacts=rsi_epoch_artifacts,
        prior_state=prior_rsi_state,
        strict=strict_rsi,
    )
    write_canon_json(rsi_state_path, rsi_result.state)
    write_canon_json(diagnostics_dir / "rsi_window_report_v1.json", rsi_result.window_report)
    if rsi_result.ignition_receipt is not None:
        write_canon_json(diagnostics_dir / "rsi_ignition_receipt_v1.json", rsi_result.ignition_receipt)

    barrier_ledger_path = state_dir / "current" / "barrier_ledger_v1.jsonl"
    if not barrier_ledger_path.exists():
        barrier_ledger_path.write_text("", encoding="utf-8")
    if rsi_result.barrier_entry is not None:
        write_jsonl_line(barrier_ledger_path, rsi_result.barrier_entry)
    (diagnostics_dir / "barrier_ledger_v1.jsonl").write_text(
        barrier_ledger_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    integrity_state_path = state_dir / "current" / "rsi_integrity_tracker_state_v1.json"
    prior_integrity_state = load_canon_json(integrity_state_path) if integrity_state_path.exists() else None
    barrier_entries = _load_jsonl_payloads(barrier_ledger_path)
    eval_budget_reports: dict[str, Any] = {}
    eval_budget_hashes: dict[str, str] = {}
    mining_report_hashes: set[str] = set()
    family_semantics_reports: dict[str, Any] = {}
    family_semantics_hashes: dict[str, str] = {}
    instance_specs_reports: dict[str, Any] = {}
    translation_certs: dict[str, Any] = {}
    translation_cert_hashes: dict[str, str] = {}
    epoch_dirs = _list_epoch_dirs(state_dir, out_dir)
    seen_epochs: set[str] = set()
    for epoch_dir in epoch_dirs:
        if epoch_dir.name in seen_epochs:
            continue
        seen_epochs.add(epoch_dir.name)
        diag_dir = epoch_dir / "diagnostics"
        eval_path = diag_dir / "eval_budget_report_v1.json"
        if eval_path.exists():
            report = load_canon_json(eval_path)
            report_epoch = report.get("epoch_id")
            if not isinstance(report_epoch, str):
                report_epoch = epoch_dir.name
            eval_budget_reports[report_epoch] = report
            eval_budget_hashes[report_epoch] = _hash_file(eval_path)
        mining_path = diag_dir / "macro_mining_report_v1.json"
        if mining_path.exists():
            mining_report_hashes.add(_hash_file(mining_path))
        sem_path = diag_dir / "family_semantics_report_v1.json"
        if sem_path.exists():
            report = load_canon_json(sem_path)
            report_epoch = report.get("epoch_id")
            if not isinstance(report_epoch, str):
                report_epoch = epoch_dir.name
            family_semantics_reports[report_epoch] = report
            family_semantics_hashes[report_epoch] = _hash_file(sem_path)
        specs_path = diag_dir / "instance_specs_v1.json"
        if specs_path.exists():
            instance_specs_reports[epoch_dir.name] = load_canon_json(specs_path)
        cert_path = diag_dir / "translation_cert_v1.json"
        if cert_path.exists():
            cert = load_canon_json(cert_path)
            patch_id = cert.get("patch_id")
            if isinstance(patch_id, str):
                translation_certs[patch_id] = cert
                translation_cert_hashes[patch_id] = _hash_file(cert_path)
        cert_dir = diag_dir / "meta_patch_certs"
        if cert_dir.exists():
            for path in sorted(cert_dir.glob("*.translation_cert_v1.json")):
                cert = load_canon_json(path)
                patch_id = cert.get("patch_id")
                if isinstance(patch_id, str) and patch_id not in translation_certs:
                    translation_certs[patch_id] = cert
                    translation_cert_hashes[patch_id] = _hash_file(path)

    macro_ledger_events = load_macro_ledger(state_dir / "current" / "macro_ledger_v1.jsonl")
    macro_def_map = {
        macro.get("macro_id"): macro
        for macro in load_macro_defs(state_dir / "current" / "macros")
        if isinstance(macro.get("macro_id"), str)
    }

    integrity_epoch_artifacts = {
        "epoch_id": epoch_id,
        "meta": meta,
        "rsi_window_report": rsi_result.window_report,
        "rsi_window_report_hash": _hash_file(diagnostics_dir / "rsi_window_report_v1.json"),
        "rsi_ignition_receipt": rsi_result.ignition_receipt,
        "rsi_ignition_receipt_hash": _hash_file(diagnostics_dir / "rsi_ignition_receipt_v1.json")
        if (diagnostics_dir / "rsi_ignition_receipt_v1.json").exists()
        else None,
        "barrier_ledger_entries": barrier_entries,
        "eval_budget_reports": eval_budget_reports,
        "eval_budget_report_hashes": eval_budget_hashes,
        "macro_ledger_events": macro_ledger_events,
        "macro_defs": macro_def_map,
        "mining_report_hashes": mining_report_hashes,
    }

    integrity_result = update_rsi_integrity_tracker(
        constants=constants,
        epoch_artifacts=integrity_epoch_artifacts,
        prior_state=prior_integrity_state,
        strict=strict_integrity,
    )
    write_canon_json(integrity_state_path, integrity_result.state)
    write_canon_json(diagnostics_dir / "rsi_integrity_window_report_v1.json", integrity_result.window_report)
    if integrity_result.integrity_receipt is not None:
        write_canon_json(diagnostics_dir / "rsi_integrity_receipt_v1.json", integrity_result.integrity_receipt)

    portfolio_state_path = state_dir / "current" / "rsi_portfolio_tracker_state_v1.json"
    prior_portfolio_state = load_canon_json(portfolio_state_path) if portfolio_state_path.exists() else None
    state_ledger_events = _load_state_ledger_events(state_dir)
    portfolio_epoch_artifacts = {
        "epoch_id": epoch_id,
        "meta": meta,
        "rsi_integrity_window_report": integrity_result.window_report,
        "rsi_integrity_receipt": integrity_result.integrity_receipt,
        "rsi_integrity_receipt_hash": _hash_file(diagnostics_dir / "rsi_integrity_receipt_v1.json")
        if (diagnostics_dir / "rsi_integrity_receipt_v1.json").exists()
        else None,
        "rsi_window_report_hash": _hash_file(diagnostics_dir / "rsi_window_report_v1.json"),
        "barrier_ledger_entries": barrier_entries,
        "state_ledger_events": state_ledger_events,
        "family_semantics_reports": family_semantics_reports,
        "family_semantics_report_hashes": family_semantics_hashes,
        "instance_specs_reports": instance_specs_reports,
        "translation_certs": translation_certs,
        "translation_cert_hashes": translation_cert_hashes,
    }
    portfolio_result = update_rsi_portfolio_tracker(
        constants=constants,
        epoch_artifacts=portfolio_epoch_artifacts,
        prior_state=prior_portfolio_state,
        strict=strict_portfolio,
    )
    write_canon_json(portfolio_state_path, portfolio_result.state)
    write_canon_json(diagnostics_dir / "rsi_portfolio_window_report_v1.json", portfolio_result.window_report)
    if portfolio_result.portfolio_receipt is not None:
        write_canon_json(diagnostics_dir / "rsi_portfolio_receipt_v1.json", portfolio_result.portfolio_receipt)

    receipt_artifacts = [
        {"name": "epoch_commit_v1.json", "hash": _hash_file(out_dir / "epoch_commit_v1.json")},
        {"name": "success_matrix.json", "hash": _hash_file(out_dir / "success_matrix.json")},
        {"name": "selection.json", "hash": _hash_file(out_dir / "selection.json")},
        {"name": "worstcase_report_v1.json", "hash": _hash_file(diagnostics_dir / "worstcase_report_v1.json")},
        {"name": "dominance_witness_v1.json", "hash": _hash_file(diagnostics_dir / "dominance_witness_v1.json")},
        {"name": "eval_budget_report_v1.json", "hash": _hash_file(diagnostics_dir / "eval_budget_report_v1.json")},
        {"name": "rsi_window_report_v1.json", "hash": _hash_file(diagnostics_dir / "rsi_window_report_v1.json")},
        {"name": "rsi_integrity_window_report_v1.json", "hash": _hash_file(diagnostics_dir / "rsi_integrity_window_report_v1.json")},
        {"name": "rsi_portfolio_window_report_v1.json", "hash": _hash_file(diagnostics_dir / "rsi_portfolio_window_report_v1.json")},
        {"name": "barrier_ledger_v1.jsonl", "hash": _hash_file(diagnostics_dir / "barrier_ledger_v1.jsonl")},
    ]
    ignition_receipt_path = diagnostics_dir / "rsi_ignition_receipt_v1.json"
    if ignition_receipt_path.exists():
        receipt_artifacts.append(
            {"name": "rsi_ignition_receipt_v1.json", "hash": _hash_file(ignition_receipt_path)}
        )
    integrity_receipt_path = diagnostics_dir / "rsi_integrity_receipt_v1.json"
    if integrity_receipt_path.exists():
        receipt_artifacts.append(
            {"name": "rsi_integrity_receipt_v1.json", "hash": _hash_file(integrity_receipt_path)}
        )
    portfolio_receipt_path = diagnostics_dir / "rsi_portfolio_receipt_v1.json"
    if portfolio_receipt_path.exists():
        receipt_artifacts.append(
            {"name": "rsi_portfolio_receipt_v1.json", "hash": _hash_file(portfolio_receipt_path)}
        )
    sem_path = diagnostics_dir / "family_semantics_report_v1.json"
    if sem_path.exists():
        receipt_artifacts.append(
            {"name": "family_semantics_report_v1.json", "hash": _hash_file(sem_path)}
        )
    meta_patch_report_path = diagnostics_dir / "meta_patch_admission_report_v1.json"
    if meta_patch_report_path.exists():
        receipt_artifacts.append(
            {"name": "meta_patch_admission_report_v1.json", "hash": _hash_file(meta_patch_report_path)}
        )
    meta_patch_receipt_path = diagnostics_dir / "meta_patch_admit_receipt_v1.json"
    if meta_patch_receipt_path.exists():
        receipt_artifacts.append(
            {"name": "meta_patch_admit_receipt_v1.json", "hash": _hash_file(meta_patch_receipt_path)}
        )
    translation_cert_path = diagnostics_dir / "translation_cert_v1.json"
    if translation_cert_path.exists():
        receipt_artifacts.append(
            {"name": "translation_cert_v1.json", "hash": _hash_file(translation_cert_path)}
        )

    receipt_payload = {
        "schema": "receipt_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "x-meta": meta,
        "artifacts": receipt_artifacts,
        "signature": {
            "alg": "none",
            "key_id": "none",
            "signature_base64": "",
        },
    }
    receipt_payload["receipt_hash"] = sha256_prefixed(canon_bytes(receipt_payload))
    write_canon_json(out_dir / "receipts" / "receipt_base.json", receipt_payload)

    # Witness ledger (append-only)
    state_ledger_path = state_dir / "current" / "witness_ledger_v1.jsonl"
    if not state_ledger_path.exists():
        state_ledger_path.write_text("", encoding="utf-8")
    ledger_lines = load_ledger_lines(state_ledger_path)
    head_hash = verify_ledger_chain(ledger_lines)
    for witness_hash in witness_hashes:
        witness_path = diagnostics_dir / "witnesses" / f"{witness_hash.split(':', 1)[1]}.json"
        witness_payload = load_canon_json(witness_path)
        line = build_ledger_line(
            witness=witness_payload,
            producing_receipt_hash=receipt_payload["receipt_hash"],
            origin_epoch_id=epoch_id,
            prev_line_hash=head_hash,
        )
        append_ledger_line(state_ledger_path, line)
        head_hash = line["line_hash"]
        ledger_lines.append(line)

    write_ledger_head(state_dir / "current" / "witness_ledger_head_v1.json", head_hash, len(ledger_lines))
    ledger_out = diagnostics_dir / "witness_ledger_v1.jsonl"
    ledger_out.write_text(state_ledger_path.read_text(encoding="utf-8"), encoding="utf-8")
    write_ledger_head(diagnostics_dir / "witness_ledger_head_v1.json", head_hash, len(ledger_lines))
    set_current_meter(None)
