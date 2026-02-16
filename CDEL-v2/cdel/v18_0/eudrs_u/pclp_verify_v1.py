"""PCLP bundle verifier (v1).

This module implements the proof-carrying verification path for QXRL QRE-only.

Fail-closed + deterministic:
  - all JSON must be GCJ-1 canonical
  - schema-validated where applicable
  - any failure maps to exactly one primary PCLP reason code
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from ..omega_common_v1 import repo_root, require_no_absolute_paths, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, verify_artifact_ref_v1
from .eudrs_u_common_v1 import SCHEMA_ACTIVE_ROOT_TUPLE_REF_V1, load_active_root_tuple_pointer
from .eudrs_u_hash_v1 import gcj1_loads_and_verify_canonical, sha256_prefixed
from .pclp_common_v1 import (
    DC1_ID_Q32_V1,
    EUDRSU_PCLP_BINDING_MISMATCH,
    EUDRSU_PCLP_CONFIG_MISMATCH,
    EUDRSU_PCLP_PROOF_INVALID,
    EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH,
    EUDRSU_PCLP_SCHEMA_INVALID,
    EUDRSU_PCLP_UNSUPPORTED_MODE,
    PROOF_SYSTEM_ID_STARK_VM_V1,
    SCHEMA_PCLP_BUNDLE_V1,
    SCHEMA_VPVM_CONFIG_V1,
    SCHEMA_VPVM_PUBLIC_INPUTS_V1,
    VPVM_ID_Q32_V1,
    bytes32_to_hex64,
    compute_self_hash_id_omit,
    derive_pclp_tails_v1,
)
from .qxrl_common_v1 import (
    DOT_KIND_SHIFT_EACH,
    ENCODER_KIND_QRE_V1,
    INVSQRT_ITERS_PHASE5_U32,
    OPTIMIZER_KIND_ADAMW_Q32_V1,
    OPTIMIZER_KIND_SGD_MOMENTUM_Q32_V1,
    SCHEMA_QXRL_DATASET_MANIFEST_V1,
    SCHEMA_QXRL_EVAL_MANIFEST_V1,
    SCHEMA_QXRL_EVAL_SCORECARD_V1,
    SCHEMA_QXRL_MODEL_MANIFEST_V1,
    SCHEMA_QXRL_TRAINING_MANIFEST_V1,
    hex64_to_bytes32,
    parse_qxrl_invsqrt_lut_manifest_v1,
)
from .qxrl_dataset_v1 import load_and_verify_qxrl_dataset_v1
from .qxrl_forward_qre_v1 import parse_qxrl_model_manifest_v1
from .qxrl_opset_math_v1 import div_q32_pos_rne_v1, invsqrt_q32_nr_lut_v1, parse_invsqrt_lut_bin_v1
from .qxrl_train_replay_v1 import load_and_verify_weights_manifest_v1, parse_and_verify_training_manifest_v1
from .vpvm_stark_verifier_v1 import verify_stark_vm_proof_v1

_OPSET_ID_RE = re.compile(r"^opset:eudrs_u_v1:sha256:[0-9a-f]{64}$")


def _load_json_from_loader(registry_loader: Callable[[dict[str, str]], bytes], ref: dict[str, str]) -> dict[str, Any]:
    raw = bytes(registry_loader(ref))
    obj = gcj1_loads_and_verify_canonical(raw)
    if not isinstance(obj, dict):
        raise ValueError("not dict")
    require_no_absolute_paths(obj)
    return dict(obj)


def _artifact_id(ref: dict[str, Any]) -> str:
    return str(ref.get("artifact_id", "")).strip()


def _load_prev_active_root_tuple(*, base_repo_root: Path) -> dict[str, Any]:
    ptr = load_active_root_tuple_pointer(root=base_repo_root)
    if ptr is None:
        raise ValueError("missing active root tuple pointer")
    if str(ptr.get("schema_id", "")).strip() != SCHEMA_ACTIVE_ROOT_TUPLE_REF_V1:
        raise ValueError("bad active root tuple pointer schema")
    active_ref = require_artifact_ref_v1(ptr.get("active_root_tuple"))
    active_path = verify_artifact_ref_v1(artifact_ref=active_ref, base_dir=base_repo_root)
    root_tuple = gcj1_loads_and_verify_canonical(active_path.read_bytes())
    if not isinstance(root_tuple, dict):
        raise ValueError("active root tuple not dict")
    require_no_absolute_paths(root_tuple)
    return dict(root_tuple)


def _load_weights_manifest_from_repo(*, wroot_ref: dict[str, str], base_repo_root: Path) -> tuple[str, Any]:
    wroot_ref = require_artifact_ref_v1(wroot_ref)
    wroot_path = verify_artifact_ref_v1(artifact_ref=wroot_ref, base_dir=base_repo_root, expected_relpath_prefix="polymath/registry/eudrs_u/")
    wroot_obj = gcj1_loads_and_verify_canonical(wroot_path.read_bytes())
    if not isinstance(wroot_obj, dict):
        raise ValueError("weights manifest not dict")
    require_no_absolute_paths(wroot_obj)

    def _repo_loader(ref: dict[str, str]) -> bytes:
        path = verify_artifact_ref_v1(artifact_ref=ref, base_dir=base_repo_root, expected_relpath_prefix="polymath/registry/eudrs_u/")
        return path.read_bytes()

    weights = load_and_verify_weights_manifest_v1(weights_manifest_obj=dict(wroot_obj), registry_loader=_repo_loader)
    return str(wroot_ref.get("artifact_id", "")).strip(), weights


def _load_weights_manifest_from_registry(
    *,
    wroot_ref: dict[str, str],
    registry_loader: Callable[[dict[str, str]], bytes],
) -> tuple[str, Any]:
    wroot_ref = require_artifact_ref_v1(wroot_ref)
    wroot_obj = _load_json_from_loader(registry_loader, wroot_ref)
    weights = load_and_verify_weights_manifest_v1(weights_manifest_obj=dict(wroot_obj), registry_loader=registry_loader)
    return str(wroot_ref.get("artifact_id", "")).strip(), weights


def verify_pclp_bundle_v1(
    *,
    root_tuple_obj: dict[str, Any],
    system_manifest_obj: dict[str, Any],
    determinism_cert_obj: dict[str, Any],
    registry_loader: Callable[[dict[str, str]], bytes],
    base_repo_root: Path | None = None,
) -> tuple[bool, str]:
    """Verify a proof-carrying bundle referenced from `determinism_cert_v1.pclp`."""

    base_repo_root = repo_root().resolve() if base_repo_root is None else Path(base_repo_root).resolve()

    try:
        # Determinism cert baseline + pclp object.
        if str(determinism_cert_obj.get("schema_id", "")).strip() != "determinism_cert_v1":
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        if str(determinism_cert_obj.get("dc1_id", "")).strip() != DC1_ID_Q32_V1:
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        opset_id = str(determinism_cert_obj.get("opset_id", "")).strip()
        if _OPSET_ID_RE.fullmatch(opset_id) is None:
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        qxrl = determinism_cert_obj.get("qxrl")
        if not isinstance(qxrl, dict):
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        # Legacy tails remain required for audit/replay mode, but proof-mode uses PCLP tails.
        legacy_h_train_tail32_hex = str(qxrl.get("h_train_tail32_hex", "")).strip()
        legacy_h_eval_tail32_hex = str(qxrl.get("h_eval_tail32_hex", "")).strip()
        _ = hex64_to_bytes32(legacy_h_train_tail32_hex, reason=EUDRSU_PCLP_SCHEMA_INVALID)
        _ = hex64_to_bytes32(legacy_h_eval_tail32_hex, reason=EUDRSU_PCLP_SCHEMA_INVALID)

        qxrl_math = qxrl.get("math")
        if not isinstance(qxrl_math, dict):
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        cert_dot_kind = str(qxrl_math.get("dot_kind", "")).strip()
        cert_div_kind = str(qxrl_math.get("div_kind", "")).strip()
        cert_invsqrt_kind = str(qxrl_math.get("invsqrt_kind", "")).strip()
        cert_lut_manifest_ref = require_artifact_ref_v1(qxrl_math.get("invsqrt_lut_manifest_ref"))
        cert_invsqrt_iters_u32 = qxrl_math.get("invsqrt_iters_u32")
        if not isinstance(cert_invsqrt_iters_u32, int) or int(cert_invsqrt_iters_u32) != int(INVSQRT_ITERS_PHASE5_U32):
            return False, EUDRSU_PCLP_SCHEMA_INVALID

        pclp = determinism_cert_obj.get("pclp")
        if not isinstance(pclp, dict):
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        if set(pclp.keys()) != {"pclp_bundle_ref", "proof_mode", "h_train_pclp_tail32_hex", "h_eval_pclp_tail32_hex"}:
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        if str(pclp.get("proof_mode", "")).strip() != "PCLP_STARK_VM_V1":
            return False, EUDRSU_PCLP_UNSUPPORTED_MODE
        h_train_pclp_tail32_hex = str(pclp.get("h_train_pclp_tail32_hex", "")).strip()
        h_eval_pclp_tail32_hex = str(pclp.get("h_eval_pclp_tail32_hex", "")).strip()
        _ = hex64_to_bytes32(h_train_pclp_tail32_hex, reason=EUDRSU_PCLP_SCHEMA_INVALID)
        _ = hex64_to_bytes32(h_eval_pclp_tail32_hex, reason=EUDRSU_PCLP_SCHEMA_INVALID)
        pclp_bundle_ref = require_artifact_ref_v1(pclp.get("pclp_bundle_ref"))

        # System manifest QXRL bindings.
        qxrl_bind = system_manifest_obj.get("qxrl")
        if not isinstance(qxrl_bind, dict):
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        model_ref = require_artifact_ref_v1(qxrl_bind.get("model_manifest_ref"))
        dataset_ref = require_artifact_ref_v1(qxrl_bind.get("dataset_manifest_ref"))
        eval_ref = require_artifact_ref_v1(qxrl_bind.get("eval_manifest_ref"))

        # Load + validate model manifest (QRE-only in v1).
        model_obj = _load_json_from_loader(registry_loader, model_ref)
        validate_schema(model_obj, SCHEMA_QXRL_MODEL_MANIFEST_V1)
        model = parse_qxrl_model_manifest_v1(model_obj)
        if str(model.encoder_kind).strip() != ENCODER_KIND_QRE_V1:
            return False, EUDRSU_PCLP_UNSUPPORTED_MODE
        # Proof mode only supports SHIFT_EACH dot semantics (matches vpvm_q32_v1 MUL_Q32_SAT).
        if str(model.dot_kind).strip() != DOT_KIND_SHIFT_EACH:
            return False, EUDRSU_PCLP_UNSUPPORTED_MODE

        # Bind determinism cert math semantics to model manifest.
        if str(cert_dot_kind).strip() != str(model.dot_kind).strip():
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        if str(cert_div_kind).strip() != str(model.div_kind).strip():
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        if str(cert_invsqrt_kind).strip() != str(model.invsqrt_kind).strip():
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        if dict(cert_lut_manifest_ref) != dict(model.invsqrt_lut_manifest_ref):
            return False, EUDRSU_PCLP_SCHEMA_INVALID

        # Phase 5: LUT pinning + opset math semantics vectors.
        lut_manifest_obj = _load_json_from_loader(registry_loader, dict(model.invsqrt_lut_manifest_ref))
        lut_manifest_parsed = parse_qxrl_invsqrt_lut_manifest_v1(dict(lut_manifest_obj))
        if str(lut_manifest_parsed.get("opset_id", "")).strip() != str(model.opset_id).strip():
            return False, EUDRSU_PCLP_BINDING_MISMATCH
        lut_ref = dict(lut_manifest_parsed.get("lut_ref"))
        lut_bytes = bytes(registry_loader(lut_ref))
        lut_table = parse_invsqrt_lut_bin_v1(lut_bytes=lut_bytes)

        Q32_ONE = 1 << 32
        inv_expected = {
            1 * Q32_ONE: 4294967295,
            2 * Q32_ONE: 3037000499,
            4 * Q32_ONE: 2147483647,
            9 * Q32_ONE: 1431655764,
        }
        for x, y_exp in inv_expected.items():
            y = invsqrt_q32_nr_lut_v1(x_q32_pos_s64=int(x), lut_table_q32_s64=lut_table, ctr=None)
            if int(y) != int(y_exp):
                return False, EUDRSU_PCLP_BINDING_MISMATCH
        if div_q32_pos_rne_v1(numer_q32_s64=Q32_ONE, denom_q32_pos_s64=3 * Q32_ONE, ctr=None) != 1431655765:
            return False, EUDRSU_PCLP_SCHEMA_INVALID

        # Load dataset + eval manifests + dataset examples (used for commitments).
        dataset_obj = _load_json_from_loader(registry_loader, dataset_ref)
        validate_schema(dataset_obj, SCHEMA_QXRL_DATASET_MANIFEST_V1)
        eval_obj = _load_json_from_loader(registry_loader, eval_ref)
        validate_schema(eval_obj, SCHEMA_QXRL_EVAL_MANIFEST_V1)
        examples, _dataset_root_hash32 = load_and_verify_qxrl_dataset_v1(dataset_manifest_obj=dataset_obj, registry_loader=registry_loader)

        # Load training manifest (optimizer kind restrictions preserved).
        training_manifest_ref = require_artifact_ref_v1(qxrl.get("training_manifest_ref"))
        training_obj = _load_json_from_loader(registry_loader, training_manifest_ref)
        validate_schema(training_obj, SCHEMA_QXRL_TRAINING_MANIFEST_V1)
        training_obj = parse_and_verify_training_manifest_v1(training_obj)
        optimizer_kind = str(training_obj.get("optimizer_kind", "")).strip()
        if optimizer_kind == OPTIMIZER_KIND_ADAMW_Q32_V1:
            return False, EUDRSU_PCLP_UNSUPPORTED_MODE
        if optimizer_kind != OPTIMIZER_KIND_SGD_MOMENTUM_Q32_V1:
            return False, EUDRSU_PCLP_SCHEMA_INVALID

        # Bind training manifest refs to system manifest refs (artifact_id equality).
        if str(training_obj.get("model_manifest_ref", {}).get("artifact_id", "")).strip() != _artifact_id(model_ref):
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        if str(training_obj.get("dataset_manifest_ref", {}).get("artifact_id", "")).strip() != _artifact_id(dataset_ref):
            return False, EUDRSU_PCLP_SCHEMA_INVALID

        # Resolve wroot_before from active root tuple in the repo (same as legacy replay semantics).
        prev_root_tuple = _load_prev_active_root_tuple(base_repo_root=base_repo_root)
        init_wroot_ref = require_artifact_ref_v1(prev_root_tuple.get("wroot"))
        wroot_before_id, weights_before = _load_weights_manifest_from_repo(wroot_ref=init_wroot_ref, base_repo_root=base_repo_root)

        # Load wroot_after weights from staged registry root tuple ref.
        wroot_after_ref = require_artifact_ref_v1(root_tuple_obj.get("wroot"))
        wroot_after_id, weights_after = _load_weights_manifest_from_registry(wroot_ref=wroot_after_ref, registry_loader=registry_loader)

        # Load + validate PCLP bundle.
        bundle_obj = _load_json_from_loader(registry_loader, pclp_bundle_ref)
        validate_schema(bundle_obj, SCHEMA_PCLP_BUNDLE_V1)
        if str(bundle_obj.get("schema_id", "")).strip() != SCHEMA_PCLP_BUNDLE_V1:
            return False, EUDRSU_PCLP_SCHEMA_INVALID

        # Bundle self-hash id (omit field rule).
        bundle_id = str(bundle_obj.get("pclp_bundle_id", "")).strip()
        if bundle_id != compute_self_hash_id_omit(bundle_obj, id_field="pclp_bundle_id"):
            return False, EUDRSU_PCLP_SCHEMA_INVALID

        if str(bundle_obj.get("proof_system_id", "")).strip() != PROOF_SYSTEM_ID_STARK_VM_V1:
            return False, EUDRSU_PCLP_UNSUPPORTED_MODE
        if str(bundle_obj.get("vpvm_id", "")).strip() != VPVM_ID_Q32_V1:
            return False, EUDRSU_PCLP_UNSUPPORTED_MODE

        # Binding checks: bundle <-> determinism cert / system manifest / root tuple.
        bindings = dict(bundle_obj.get("bindings", {}))
        expected_outputs = dict(bundle_obj.get("expected_outputs", {}))

        if str(bindings.get("opset_id", "")).strip() != opset_id:
            return False, EUDRSU_PCLP_BINDING_MISMATCH
        if str(bindings.get("dc1_id", "")).strip() != DC1_ID_Q32_V1:
            return False, EUDRSU_PCLP_BINDING_MISMATCH
        if _artifact_id(bindings.get("training_manifest_ref", {})) != _artifact_id(training_manifest_ref):
            return False, EUDRSU_PCLP_BINDING_MISMATCH
        if _artifact_id(bindings.get("dataset_manifest_ref", {})) != _artifact_id(dataset_ref):
            return False, EUDRSU_PCLP_BINDING_MISMATCH
        if _artifact_id(bindings.get("eval_manifest_ref", {})) != _artifact_id(eval_ref):
            return False, EUDRSU_PCLP_BINDING_MISMATCH
        if _artifact_id(bindings.get("invsqrt_lut_manifest_ref", {})) != _artifact_id(cert_lut_manifest_ref):
            return False, EUDRSU_PCLP_BINDING_MISMATCH

        if _artifact_id(expected_outputs.get("wroot_after_ref", {})) != _artifact_id(wroot_after_ref):
            return False, EUDRSU_PCLP_BINDING_MISMATCH

        scorecard_ref = require_artifact_ref_v1(eval_obj.get("scorecard_ref"))
        if _artifact_id(expected_outputs.get("scorecard_ref", {})) != _artifact_id(scorecard_ref):
            return False, EUDRSU_PCLP_BINDING_MISMATCH

        # Ensure scorecard artifact exists + schema-valid.
        scorecard_obj = _load_json_from_loader(registry_loader, scorecard_ref)
        validate_schema(scorecard_obj, SCHEMA_QXRL_EVAL_SCORECARD_V1)

        if str(expected_outputs.get("h_train_tail32_hex", "")).strip() != h_train_pclp_tail32_hex:
            return False, EUDRSU_PCLP_BINDING_MISMATCH
        if str(expected_outputs.get("h_eval_tail32_hex", "")).strip() != h_eval_pclp_tail32_hex:
            return False, EUDRSU_PCLP_BINDING_MISMATCH

        # Load VPVM config + public inputs + program + proof artifacts.
        vpvm_config_ref = require_artifact_ref_v1(bundle_obj.get("vpvm_config_ref"))
        vpvm_public_inputs_ref = require_artifact_ref_v1(bundle_obj.get("public_inputs_ref"))
        program_bin_ref = require_artifact_ref_v1(bundle_obj.get("program_bin_ref"))
        proof_bin_ref = require_artifact_ref_v1(bundle_obj.get("proof_bin_ref"))

        vpvm_config_obj = _load_json_from_loader(registry_loader, vpvm_config_ref)
        validate_schema(vpvm_config_obj, SCHEMA_VPVM_CONFIG_V1)
        if str(vpvm_config_obj.get("schema_id", "")).strip() != SCHEMA_VPVM_CONFIG_V1:
            return False, EUDRSU_PCLP_SCHEMA_INVALID

        cfg_id = str(vpvm_config_obj.get("vpvm_config_id", "")).strip()
        if cfg_id != compute_self_hash_id_omit(vpvm_config_obj, id_field="vpvm_config_id"):
            return False, EUDRSU_PCLP_CONFIG_MISMATCH

        # Pinned config checks (in addition to schema-level consts).
        if str(vpvm_config_obj.get("trace", {}).get("opset_id", "")).strip() != opset_id:
            return False, EUDRSU_PCLP_CONFIG_MISMATCH
        if int(vpvm_config_obj.get("trace", {}).get("max_steps_u32", 0)) <= 0:
            return False, EUDRSU_PCLP_CONFIG_MISMATCH

        vpvm_public_inputs_obj = _load_json_from_loader(registry_loader, vpvm_public_inputs_ref)
        validate_schema(vpvm_public_inputs_obj, SCHEMA_VPVM_PUBLIC_INPUTS_V1)
        if str(vpvm_public_inputs_obj.get("schema_id", "")).strip() != SCHEMA_VPVM_PUBLIC_INPUTS_V1:
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        if str(vpvm_public_inputs_obj.get("vpvm_id", "")).strip() != VPVM_ID_Q32_V1:
            return False, EUDRSU_PCLP_UNSUPPORTED_MODE
        if str(vpvm_public_inputs_obj.get("vpvm_config_id", "")).strip() != cfg_id:
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH

        program_bytes = bytes(registry_loader(program_bin_ref))
        program_id = sha256_prefixed(program_bytes)
        if str(vpvm_public_inputs_obj.get("program_id", "")).strip() != str(program_id).strip():
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH

        proof_bytes = bytes(registry_loader(proof_bin_ref))

        # Public input pinning checks (ids/tails/scorecard).
        pi = vpvm_public_inputs_obj.get("public_inputs")
        if not isinstance(pi, dict):
            return False, EUDRSU_PCLP_SCHEMA_INVALID
        pi = dict(pi)

        if str(pi.get("opset_id", "")).strip() != opset_id:
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if str(pi.get("dc1_id", "")).strip() != DC1_ID_Q32_V1:
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if str(pi.get("training_manifest_id", "")).strip() != _artifact_id(training_manifest_ref):
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if str(pi.get("dataset_manifest_id", "")).strip() != _artifact_id(dataset_ref):
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if str(pi.get("eval_manifest_id", "")).strip() != _artifact_id(eval_ref):
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if str(pi.get("lut_manifest_id", "")).strip() != _artifact_id(cert_lut_manifest_ref):
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if str(pi.get("wroot_before_id", "")).strip() != str(wroot_before_id).strip():
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if str(pi.get("wroot_after_id", "")).strip() != str(wroot_after_id).strip():
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if str(pi.get("h_train_tail32_hex_expected", "")).strip() != h_train_pclp_tail32_hex:
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if str(pi.get("h_eval_tail32_hex_expected", "")).strip() != h_eval_pclp_tail32_hex:
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if str(pi.get("scorecard_artifact_id_expected", "")).strip() != _artifact_id(scorecard_ref):
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH

        # v1 caps: must be well-formed and deterministic.
        caps = pi.get("caps")
        if not isinstance(caps, dict):
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        mem_caps = caps.get("mem")
        if not isinstance(mem_caps, dict):
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        max_addr_u64 = mem_caps.get("max_addr_u64")
        allowed_segs_u8 = mem_caps.get("allowed_segs_u8")
        seg_limits = mem_caps.get("seg_limits")
        if not isinstance(max_addr_u64, int) or max_addr_u64 < 0 or max_addr_u64 > 0xFFFFFFFFFFFFFFFF:
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if not isinstance(allowed_segs_u8, list) or not allowed_segs_u8:
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if allowed_segs_u8 != sorted(set(int(x) for x in allowed_segs_u8)):
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if not isinstance(seg_limits, list) or not seg_limits:
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        segs_seen: list[int] = []
        for row in seg_limits:
            if not isinstance(row, dict):
                return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
            s = row.get("seg_u8")
            m = row.get("max_addr_u64")
            if not isinstance(s, int) or s < 0 or s > 255:
                return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
            if not isinstance(m, int) or m < 0 or m > int(max_addr_u64):
                return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
            segs_seen.append(int(s))
        if segs_seen != sorted(segs_seen):
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH
        if sorted(set(segs_seen)) != list(allowed_segs_u8):
            return False, EUDRSU_PCLP_PUBLIC_INPUT_MISMATCH

        # Proof-mode tails are verifier-recomputable (Option 2); enforce determinism cert matches.
        poseidon_params_ref = require_artifact_ref_v1(vpvm_config_obj.get("hash", {}).get("poseidon_params_ref"))
        poseidon_params_bin = bytes(registry_loader(poseidon_params_ref))
        h_train_calc32, h_eval_calc32 = derive_pclp_tails_v1(
            poseidon_params_bin=poseidon_params_bin,
            public_inputs_base_hash32=hex64_to_bytes32(str(vpvm_public_inputs_obj.get("public_inputs_base_hash32_hex", "")).strip()),
            wroot_before_id=str(wroot_before_id),
            wroot_after_id=str(wroot_after_id),
            program_id=str(program_id),
            scorecard_artifact_id=str(_artifact_id(scorecard_ref)),
            eval_manifest_id=str(_artifact_id(eval_ref)),
        )
        if bytes32_to_hex64(h_train_calc32) != h_train_pclp_tail32_hex:
            return False, EUDRSU_PCLP_BINDING_MISMATCH
        if bytes32_to_hex64(h_eval_calc32) != h_eval_pclp_tail32_hex:
            return False, EUDRSU_PCLP_BINDING_MISMATCH

        # Verify proof + commitments (v1 minimal verifier).
        ok, reason = verify_stark_vm_proof_v1(
            vpvm_config_obj=dict(vpvm_config_obj),
            poseidon_params_bin=bytes(poseidon_params_bin),
            vpvm_public_inputs_obj=dict(vpvm_public_inputs_obj),
            program_bytes=program_bytes,
            proof_bytes=proof_bytes,
            lut_bytes=lut_bytes,
            examples=examples,
            weights_before=weights_before,
            weights_after=weights_after,
        )
        if not ok:
            return False, str(reason)

        return True, "EUDRSU_OK"
    except Exception:
        return False, EUDRSU_PCLP_SCHEMA_INVALID


__all__ = ["verify_pclp_bundle_v1"]
