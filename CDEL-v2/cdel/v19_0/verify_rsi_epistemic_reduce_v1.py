"""Verifier for v19 epistemic reduce campaign artifacts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ..v18_0.omega_common_v1 import OmegaV18Error, canon_hash_obj, fail
from .common_v1 import ensure_sha256
from .common_v1 import validate_schema as validate_schema_v19
from .epistemic.verify_epistemic_capsule_v1 import verify_capsule_bundle
from .epistemic.verify_epistemic_certs_v1 import verify_certs_state
from .epistemic.verify_epistemic_reduce_v1 import verify_reduce
from .epistemic.usable_index_v1 import load_usable_capsule_ids, load_usable_graph_ids, load_rows as load_usable_rows
from .epistemic.retention_v1 import build_retention_artifacts


def _resolve_state(path: Path) -> Path:
    root = path.resolve()
    candidates = [
        root / "daemon" / "rsi_epistemic_reduce_v1" / "state",
        root,
    ]
    for candidate in candidates:
        if (candidate / "epistemic").is_dir():
            return candidate
    fail("SCHEMA_FAIL")
    return root


def _verify_refutation(state_root: Path) -> None:
    ref_dir = state_root / "epistemic" / "refutations"
    rows = sorted(ref_dir.glob("sha256_*.epistemic_capsule_refutation_v1.json"), key=lambda p: p.as_posix())
    if len(rows) != 1:
        fail("SCHEMA_FAIL")
    payload = json.loads(rows[0].read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if canon_hash_obj(payload) != "sha256:" + rows[0].name.split(".", 1)[0].split("_", 1)[1]:
        fail("NONDETERMINISTIC")
    validate_schema_v19(payload, "epistemic_capsule_refutation_v1")
    expected_id = canon_hash_obj({k: v for k, v in payload.items() if k != "refutation_id"})
    if str(payload.get("refutation_id", "")) != expected_id:
        fail("NONDETERMINISTIC")


def _load_single_optional(dir_path: Path, suffix: str) -> dict | None:
    rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix())
    if not rows:
        return None
    if len(rows) != 1:
        fail("SCHEMA_FAIL")
    payload = json.loads(rows[0].read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if canon_hash_obj(payload) != "sha256:" + rows[0].name.split(".", 1)[0].split("_", 1)[1]:
        fail("NONDETERMINISTIC")
    return payload


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        fail("MODE_UNSUPPORTED")

    # Hard-off replay networking even if caller sets it externally.
    os.environ["OMEGA_NET_LIVE_OK"] = "0"

    state_root = _resolve_state(state_dir)
    cap_rows = sorted((state_root / "epistemic" / "capsules").glob("sha256_*.epistemic_capsule_v1.json"), key=lambda p: p.as_posix())
    ref_rows = sorted((state_root / "epistemic" / "refutations").glob("sha256_*.epistemic_capsule_refutation_v1.json"), key=lambda p: p.as_posix())

    if cap_rows and ref_rows:
        fail("SCHEMA_FAIL")
    if not cap_rows and not ref_rows:
        fail("MISSING_STATE_INPUT")

    if ref_rows:
        _verify_refutation(state_root)
        return "VALID"

    reduce_result = verify_reduce(state_root)
    capsule_result = verify_capsule_bundle(state_root)
    if str(reduce_result.get("graph_id", "")) != str(capsule_result.get("distillate_graph_id", "")):
        fail("NONDETERMINISTIC")

    replay_root = state_root / "epistemic" / "replay_inputs"
    cert_gate_payload = _load_single_optional(replay_root / "contracts", "epistemic_cert_gate_binding_v1.json")
    cert_gate_mode = "OFF"
    objective_profile_id = "sha256:" + ("0" * 64)
    cert_profile_id = "sha256:" + ("0" * 64)
    if cert_gate_payload is not None:
        if str(cert_gate_payload.get("schema_version", "")) != "epistemic_cert_gate_binding_v1":
            fail("SCHEMA_FAIL")
        cert_gate_mode = str(cert_gate_payload.get("cert_gate_mode", "OFF")).strip().upper()
        if cert_gate_mode not in {"OFF", "WARN", "ENFORCE"}:
            fail("SCHEMA_FAIL")
        objective_profile_id = ensure_sha256(cert_gate_payload.get("objective_profile_id"), reason="SCHEMA_FAIL")
        cert_profile_id = ensure_sha256(cert_gate_payload.get("cert_profile_id", "sha256:" + ("0" * 64)), reason="SCHEMA_FAIL")

    capsule_payload = _load_single_optional(state_root / "epistemic" / "capsules", "epistemic_capsule_v1.json")
    if capsule_payload is None:
        fail("MISSING_STATE_INPUT")
    validate_schema_v19(capsule_payload, "epistemic_capsule_v1")
    capsule_id = ensure_sha256(capsule_payload.get("capsule_id"), reason="SCHEMA_FAIL")
    graph_id = ensure_sha256(capsule_payload.get("distillate_graph_id"), reason="SCHEMA_FAIL")
    usable_b = bool(capsule_payload.get("usable_b"))
    cert_gate_status = str(capsule_payload.get("cert_gate_status", "")).strip().upper()
    if cert_gate_status not in {"PASS", "WARN", "BLOCKED"}:
        fail("SCHEMA_FAIL")
    if str(reduce_result.get("strip_receipt_id", "")) != str(capsule_payload.get("strip_receipt_id", "")):
        fail("NONDETERMINISTIC")
    capsule_cert_profile_id = ensure_sha256(capsule_payload.get("cert_profile_id"), reason="SCHEMA_FAIL")
    if cert_gate_mode != "OFF" and cert_profile_id != capsule_cert_profile_id:
        fail("NONDETERMINISTIC")

    ecac_payload = _load_single_optional(state_root / "epistemic" / "certs", "epistemic_ecac_v1.json")
    eufc_payload = _load_single_optional(state_root / "epistemic" / "certs", "epistemic_eufc_v1.json")
    certs_present = ecac_payload is not None or eufc_payload is not None
    cert_valid = False
    if certs_present:
        if ecac_payload is None or eufc_payload is None:
            fail("NONDETERMINISTIC")
        if cert_gate_mode != "OFF":
            verify_certs_state(state_root, objective_profile_id=objective_profile_id)
            cert_valid = (
                str(ecac_payload.get("status", "")) == "OK"
                and str(eufc_payload.get("status", "")) == "OK"
            )
    elif cert_gate_mode == "ENFORCE":
        cert_valid = False

    _ = load_usable_rows(state_root)
    usable_capsule_ids = load_usable_capsule_ids(state_root)
    usable_graph_ids = load_usable_graph_ids(state_root)
    if usable_b:
        if capsule_id not in usable_capsule_ids or graph_id not in usable_graph_ids:
            fail("NONDETERMINISTIC")
    else:
        if capsule_id in usable_capsule_ids or graph_id in usable_graph_ids:
            fail("NONDETERMINISTIC")

    if cert_gate_mode == "OFF":
        if not usable_b or cert_gate_status != "PASS":
            fail("CERT_GATE_FAIL")
    elif cert_gate_mode == "ENFORCE":
        if cert_valid:
            if not usable_b or cert_gate_status != "PASS":
                fail("CERT_GATE_FAIL")
        else:
            if usable_b or cert_gate_status != "BLOCKED":
                fail("CERT_GATE_FAIL")
    else:  # WARN
        if cert_valid:
            if not usable_b or cert_gate_status != "PASS":
                fail("CERT_GATE_FAIL")
        else:
            if not usable_b or cert_gate_status != "WARN":
                fail("CERT_GATE_FAIL")

    retention_policy = _load_single_optional(state_root / "epistemic" / "retention", "epistemic_retention_policy_v1.json")
    if retention_policy is not None:
        validate_schema_v19(retention_policy, "epistemic_retention_policy_v1")
        policy_no_id = dict(retention_policy)
        policy_no_id.pop("policy_id", None)
        if canon_hash_obj(policy_no_id) != str(retention_policy.get("policy_id", "")):
            fail("NONDETERMINISTIC")
        manifest_payload = _load_single_optional(state_root / "epistemic" / "world" / "manifests", "world_snapshot_manifest_v1.json")
        if capsule_payload is None or manifest_payload is None:
            fail("MISSING_STATE_INPUT")
        recomputed = build_retention_artifacts(
            retention_policy=retention_policy,
            capsule=capsule_payload,
            world_manifest=manifest_payload,
            sampling_seed_u64=int(capsule_payload.get("tick_u64", 0)),
        )
        observed_deletion = _load_single_optional(state_root / "epistemic" / "retention", "epistemic_deletion_plan_v1.json")
        observed_sampling = _load_single_optional(state_root / "epistemic" / "retention", "epistemic_sampling_manifest_v1.json")
        observed_summary = _load_single_optional(state_root / "epistemic" / "retention", "epistemic_summary_proof_v1.json")
        if observed_deletion is None or observed_sampling is None or observed_summary is None:
            fail("MISSING_STATE_INPUT")
        if canon_hash_obj(observed_deletion) != canon_hash_obj(recomputed["deletion_plan"]):
            fail("NONDETERMINISTIC")
        if canon_hash_obj(observed_sampling) != canon_hash_obj(recomputed["sampling_manifest"]):
            fail("NONDETERMINISTIC")
        if canon_hash_obj(observed_summary) != canon_hash_obj(recomputed["summary_proof"]):
            fail("NONDETERMINISTIC")
    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_epistemic_reduce_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        print(verify(Path(args.state_dir), mode=str(args.mode)))
    except OmegaV18Error as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
