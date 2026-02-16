"""QXRL replay verifier (v1, Phase 4 + Phase 5).

Fail-closed verification of:
  - qxrl model/dataset/eval manifests (schema + content-addressed loads)
  - dataset segment integrity + dataset_root_hash32
  - deterministic training replay to final WRoot + H_train tail
  - deterministic evaluation replay to scorecard bytes/hash + H_eval tail + floors
  - Phase 5: opset-pinned Div/InvSqrt semantics (LUT pinning + required test vectors)
  - Phase 5: reject AdamW optimizer kind (promotions forbidden)

This module is RE2: deterministic, fail-closed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from ..omega_common_v1 import fail, repo_root, require_no_absolute_paths, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, verify_artifact_ref_v1
from .eudrs_u_common_v1 import SCHEMA_ACTIVE_ROOT_TUPLE_REF_V1, load_active_root_tuple_pointer
from .eudrs_u_hash_v1 import gcj1_loads_and_verify_canonical
from .qxrl_common_v1 import (
    EUDRSU_OK,
    INVSQRT_ITERS_PHASE5_U32,
    OPTIMIZER_KIND_ADAMW_Q32_V1,
    OPTIMIZER_KIND_SGD_MOMENTUM_Q32_V1,
    REASON_QXRL_DATASET_HASH_MISMATCH,
    REASON_QXRL_EVAL_TAIL_MISMATCH,
    REASON_QXRL_FLOOR_FAIL,
    REASON_QXRL_OPSET_LUT_MISMATCH,
    REASON_QXRL_OPTIMIZER_KIND_FORBIDDEN,
    REASON_QXRL_SCHEMA_INVALID,
    REASON_QXRL_SCORECARD_MISMATCH,
    REASON_QXRL_SEGMENT_DECODE_FAIL,
    REASON_QXRL_TRAIN_TAIL_MISMATCH,
    SCHEMA_QXRL_DATASET_MANIFEST_V1,
    SCHEMA_QXRL_EVAL_MANIFEST_V1,
    SCHEMA_QXRL_EVAL_SCORECARD_V1,
    SCHEMA_QXRL_MODEL_MANIFEST_V1,
    SCHEMA_QXRL_TRAINING_MANIFEST_V1,
    digest32_to_hex,
    hex64_to_bytes32,
    parse_qxrl_invsqrt_lut_manifest_v1,
    sha256_id_to_digest32,
)
from .qxrl_dataset_v1 import load_and_verify_qxrl_dataset_v1
from .qxrl_eval_v1 import compute_qxrl_eval_scorecard_v1
from .qxrl_forward_qre_v1 import load_qxrl_model_manifest_v1, parse_qxrl_model_manifest_v1
from .qxrl_opset_math_v1 import div_q32_pos_rne_v1, invsqrt_q32_nr_lut_v1, parse_invsqrt_lut_bin_v1
from .qxrl_train_replay_v1 import (
    WeightsManifestV1,
    load_and_verify_weights_manifest_v1,
    load_qxrl_training_manifest_v1,
    parse_and_verify_training_manifest_v1,
    replay_qxrl_training_v1,
)
from .pclp_common_v1 import EUDRSU_PCLP_UNSUPPORTED_MODE

_OPSET_ID_RE = re.compile(r"^opset:eudrs_u_v1:sha256:[0-9a-f]{64}$")


def _validate_schema(obj: dict[str, Any], schema_name: str, *, reason: str) -> None:
    try:
        validate_schema(obj, schema_name)
    except Exception:  # noqa: BLE001
        fail(reason)


def _load_json_from_loader(registry_loader: Callable[[dict[str, str]], bytes], ref: dict[str, str], *, reason: str) -> dict[str, Any]:
    raw = bytes(registry_loader(ref))
    obj = gcj1_loads_and_verify_canonical(raw)
    if not isinstance(obj, dict):
        fail(reason)
    require_no_absolute_paths(obj)
    return dict(obj)


def _load_prev_active_root_tuple(*, base_repo_root: Path) -> dict[str, Any] | None:
    ptr = load_active_root_tuple_pointer(root=base_repo_root)
    if ptr is None:
        return None
    if str(ptr.get("schema_id", "")).strip() != SCHEMA_ACTIVE_ROOT_TUPLE_REF_V1:
        fail(REASON_QXRL_SCHEMA_INVALID)
    active_ref = require_artifact_ref_v1(ptr.get("active_root_tuple"))
    active_path = verify_artifact_ref_v1(artifact_ref=active_ref, base_dir=base_repo_root)
    root_tuple = gcj1_loads_and_verify_canonical(active_path.read_bytes())
    if not isinstance(root_tuple, dict):
        fail(REASON_QXRL_SCHEMA_INVALID)
    require_no_absolute_paths(root_tuple)
    return dict(root_tuple)


def _load_weights_manifest_from_repo(*, wroot_ref: dict[str, str], base_repo_root: Path) -> tuple[str, WeightsManifestV1]:
    wroot_ref = require_artifact_ref_v1(wroot_ref)
    wroot_path = verify_artifact_ref_v1(artifact_ref=wroot_ref, base_dir=base_repo_root, expected_relpath_prefix="polymath/registry/eudrs_u/")
    wroot_bytes = wroot_path.read_bytes()
    wroot_obj = gcj1_loads_and_verify_canonical(wroot_bytes)
    if not isinstance(wroot_obj, dict):
        fail(REASON_QXRL_SCHEMA_INVALID)
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
) -> tuple[str, dict[str, Any], WeightsManifestV1]:
    wroot_ref = require_artifact_ref_v1(wroot_ref)
    wroot_obj = _load_json_from_loader(registry_loader, wroot_ref, reason=REASON_QXRL_SCHEMA_INVALID)
    weights = load_and_verify_weights_manifest_v1(weights_manifest_obj=dict(wroot_obj), registry_loader=registry_loader)
    return str(wroot_ref.get("artifact_id", "")).strip(), dict(wroot_obj), weights


def verify_qxrl_v1(
    *,
    root_tuple_obj: dict,
    system_manifest_obj: dict,
    determinism_cert_obj: dict,
    registry_loader: Callable[[dict[str, str]], bytes],
    mode: str = "full",
) -> tuple[bool, str]:
    try:
        mode_s = str(mode).strip()
        if mode_s not in {"full", "audit", "replay"}:
            # Proof-path callers use `mode` for audit semantics; reject unknown modes.
            if isinstance(determinism_cert_obj, dict) and isinstance(determinism_cert_obj.get("pclp"), dict):
                return False, EUDRSU_PCLP_UNSUPPORTED_MODE
            return False, REASON_QXRL_SCHEMA_INVALID

        # Proof-carrying path: if determinism cert references PCLP and we're not auditing,
        # verify proof artifacts and skip legacy replay.
        if mode_s != "audit" and isinstance(determinism_cert_obj, dict) and isinstance(determinism_cert_obj.get("pclp"), dict):
            from .pclp_verify_v1 import verify_pclp_bundle_v1

            ok, reason = verify_pclp_bundle_v1(
                root_tuple_obj=dict(root_tuple_obj) if isinstance(root_tuple_obj, dict) else {},
                system_manifest_obj=dict(system_manifest_obj) if isinstance(system_manifest_obj, dict) else {},
                determinism_cert_obj=dict(determinism_cert_obj),
                registry_loader=registry_loader,
            )
            return bool(ok), str(reason)

        if not isinstance(root_tuple_obj, dict) or not isinstance(system_manifest_obj, dict) or not isinstance(determinism_cert_obj, dict):
            return False, REASON_QXRL_SCHEMA_INVALID

        # Determinism cert Phase 4 required fields.
        if str(determinism_cert_obj.get("schema_id", "")).strip() != "determinism_cert_v1":
            return False, REASON_QXRL_SCHEMA_INVALID
        epoch_u64 = determinism_cert_obj.get("epoch_u64")
        if not isinstance(epoch_u64, int) or epoch_u64 < 0:
            return False, REASON_QXRL_SCHEMA_INVALID
        if str(determinism_cert_obj.get("dc1_id", "")).strip() != "dc1:q32_v1":
            return False, REASON_QXRL_SCHEMA_INVALID
        opset_id = str(determinism_cert_obj.get("opset_id", "")).strip()
        if _OPSET_ID_RE.fullmatch(opset_id) is None:
            return False, REASON_QXRL_SCHEMA_INVALID
        qxrl = determinism_cert_obj.get("qxrl")
        if not isinstance(qxrl, dict):
            return False, REASON_QXRL_SCHEMA_INVALID
        training_manifest_ref = require_artifact_ref_v1(qxrl.get("training_manifest_ref"))
        init_wroot_ref_from_cert: dict[str, str] | None = None
        if qxrl.get("initial_wroot_ref") is not None:
            try:
                init_wroot_ref_from_cert = require_artifact_ref_v1(qxrl.get("initial_wroot_ref"))
            except Exception:
                return False, REASON_QXRL_SCHEMA_INVALID
        h_train_tail32_hex = str(qxrl.get("h_train_tail32_hex", "")).strip()
        h_eval_tail32_hex = str(qxrl.get("h_eval_tail32_hex", "")).strip()
        qxrl_math = qxrl.get("math")
        if not isinstance(qxrl_math, dict):
            return False, REASON_QXRL_SCHEMA_INVALID
        cert_dot_kind = str(qxrl_math.get("dot_kind", "")).strip()
        cert_div_kind = str(qxrl_math.get("div_kind", "")).strip()
        cert_invsqrt_kind = str(qxrl_math.get("invsqrt_kind", "")).strip()
        cert_lut_manifest_ref = require_artifact_ref_v1(qxrl_math.get("invsqrt_lut_manifest_ref"))
        cert_invsqrt_iters_u32 = qxrl_math.get("invsqrt_iters_u32")
        if not isinstance(cert_invsqrt_iters_u32, int) or int(cert_invsqrt_iters_u32) != int(INVSQRT_ITERS_PHASE5_U32):
            return False, REASON_QXRL_SCHEMA_INVALID
        try:
            _ = hex64_to_bytes32(h_train_tail32_hex, reason=REASON_QXRL_SCHEMA_INVALID)
            _ = hex64_to_bytes32(h_eval_tail32_hex, reason=REASON_QXRL_SCHEMA_INVALID)
        except Exception:
            return False, REASON_QXRL_SCHEMA_INVALID

        # Load QXRL manifests from system manifest.
        qxrl_bind = system_manifest_obj.get("qxrl")
        if not isinstance(qxrl_bind, dict):
            return False, REASON_QXRL_SCHEMA_INVALID
        model_ref = require_artifact_ref_v1(qxrl_bind.get("model_manifest_ref"))
        dataset_ref = require_artifact_ref_v1(qxrl_bind.get("dataset_manifest_ref"))
        eval_ref = require_artifact_ref_v1(qxrl_bind.get("eval_manifest_ref"))

        model_obj = _load_json_from_loader(registry_loader, model_ref, reason=REASON_QXRL_SCHEMA_INVALID)
        _validate_schema(model_obj, SCHEMA_QXRL_MODEL_MANIFEST_V1, reason=REASON_QXRL_SCHEMA_INVALID)
        model = parse_qxrl_model_manifest_v1(model_obj)

        # Determinism cert must bind opset math semantics exactly to the model manifest.
        if str(cert_dot_kind).strip() != str(model.dot_kind).strip():
            return False, REASON_QXRL_SCHEMA_INVALID
        if str(cert_div_kind).strip() != str(model.div_kind).strip():
            return False, REASON_QXRL_SCHEMA_INVALID
        if str(cert_invsqrt_kind).strip() != str(model.invsqrt_kind).strip():
            return False, REASON_QXRL_SCHEMA_INVALID
        if dict(cert_lut_manifest_ref) != dict(model.invsqrt_lut_manifest_ref):
            return False, REASON_QXRL_SCHEMA_INVALID

        # Phase 5: LUT pinning + opset math semantics (required test vectors).
        try:
            lut_manifest_obj = _load_json_from_loader(registry_loader, dict(model.invsqrt_lut_manifest_ref), reason=REASON_QXRL_SCHEMA_INVALID)
            lut_manifest_parsed = parse_qxrl_invsqrt_lut_manifest_v1(dict(lut_manifest_obj))
            if str(lut_manifest_parsed.get("opset_id", "")).strip() != str(model.opset_id).strip():
                return False, REASON_QXRL_SCHEMA_INVALID

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
                    return False, REASON_QXRL_OPSET_LUT_MISMATCH

            # DivQ32_Pos_RNE_V1 test vectors (defensive; reasons remain schema invalid).
            if div_q32_pos_rne_v1(numer_q32_s64=Q32_ONE, denom_q32_pos_s64=3 * Q32_ONE, ctr=None) != 1431655765:
                return False, REASON_QXRL_SCHEMA_INVALID
            if div_q32_pos_rne_v1(numer_q32_s64=Q32_ONE + 1, denom_q32_pos_s64=1 << 33, ctr=None) != 2147483648:
                return False, REASON_QXRL_SCHEMA_INVALID
            if div_q32_pos_rne_v1(numer_q32_s64=Q32_ONE + 3, denom_q32_pos_s64=1 << 33, ctr=None) != 2147483650:
                return False, REASON_QXRL_SCHEMA_INVALID
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if REASON_QXRL_OPSET_LUT_MISMATCH in msg:
                return False, REASON_QXRL_OPSET_LUT_MISMATCH
            return False, REASON_QXRL_SCHEMA_INVALID

        dataset_obj = _load_json_from_loader(registry_loader, dataset_ref, reason=REASON_QXRL_SCHEMA_INVALID)
        _validate_schema(dataset_obj, SCHEMA_QXRL_DATASET_MANIFEST_V1, reason=REASON_QXRL_SCHEMA_INVALID)

        eval_obj = _load_json_from_loader(registry_loader, eval_ref, reason=REASON_QXRL_SCHEMA_INVALID)
        _validate_schema(eval_obj, SCHEMA_QXRL_EVAL_MANIFEST_V1, reason=REASON_QXRL_SCHEMA_INVALID)

        # Load and verify dataset segments + root hash.
        try:
            examples, dataset_root_hash32 = load_and_verify_qxrl_dataset_v1(dataset_manifest_obj=dataset_obj, registry_loader=registry_loader)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if REASON_QXRL_SEGMENT_DECODE_FAIL in msg:
                return False, REASON_QXRL_SEGMENT_DECODE_FAIL
            if REASON_QXRL_DATASET_HASH_MISMATCH in msg:
                return False, REASON_QXRL_DATASET_HASH_MISMATCH
            return False, REASON_QXRL_SCHEMA_INVALID

        # Load final WRoot weights manifest (proposed root tuple).
        wroot_ref = require_artifact_ref_v1(root_tuple_obj.get("wroot"))
        final_wroot_id, final_wroot_obj, final_weights = _load_weights_manifest_from_registry(wroot_ref=wroot_ref, registry_loader=registry_loader)

        # Verify required QXRL tensors and shapes (Phase 5: model manifest tensor_specs is authoritative).
        required_shapes = {spec.name: list(spec.shape_u32) for spec in model.tensor_specs}
        by_name = {t.name: t for t in final_weights.tensors}
        for name, shape in required_shapes.items():
            t = by_name.get(name)
            if t is None or [int(d) for d in t.shape_u32] != [int(d) for d in shape]:
                return False, REASON_QXRL_SCHEMA_INVALID

        # Load training manifest referenced from determinism cert.
        training_obj = _load_json_from_loader(registry_loader, training_manifest_ref, reason=REASON_QXRL_SCHEMA_INVALID)
        _validate_schema(training_obj, SCHEMA_QXRL_TRAINING_MANIFEST_V1, reason=REASON_QXRL_SCHEMA_INVALID)
        training_obj = parse_and_verify_training_manifest_v1(training_obj)

        # Phase 5: AdamW allowed in schema but forbidden for verifier acceptance.
        optimizer_kind = str(training_obj.get("optimizer_kind", "")).strip()
        if optimizer_kind == OPTIMIZER_KIND_ADAMW_Q32_V1:
            return False, REASON_QXRL_OPTIMIZER_KIND_FORBIDDEN
        if optimizer_kind != OPTIMIZER_KIND_SGD_MOMENTUM_Q32_V1:
            return False, REASON_QXRL_SCHEMA_INVALID

        # Bind training manifest refs to system manifest refs (artifact_id match).
        if str(training_obj.get("model_manifest_ref", {}).get("artifact_id", "")).strip() != str(model_ref.get("artifact_id", "")).strip():
            return False, REASON_QXRL_SCHEMA_INVALID
        if str(training_obj.get("dataset_manifest_ref", {}).get("artifact_id", "")).strip() != str(dataset_ref.get("artifact_id", "")).strip():
            return False, REASON_QXRL_SCHEMA_INVALID

        # Resolve initial weights.
        # Preferred: bind from staged evidence via determinism_cert.qxrl.initial_wroot_ref,
        # so replay is self-contained and independent of mutable repo active-pointer state.
        if init_wroot_ref_from_cert is not None:
            init_wroot_id, _init_wroot_obj, init_weights = _load_weights_manifest_from_registry(
                wroot_ref=init_wroot_ref_from_cert,
                registry_loader=registry_loader,
            )
        else:
            # Backward-compatible fallback for legacy certs that do not bind init WRoot.
            base = repo_root().resolve()
            prev_root_tuple = _load_prev_active_root_tuple(base_repo_root=base)
            if prev_root_tuple is None:
                # Bootstrap mode (no active tuple yet): bind initial weights to the
                # proposed WRoot and require replay to converge to the same final WRoot.
                init_wroot_id = str(final_wroot_id).strip()
                init_weights = final_weights
            else:
                init_wroot_ref = require_artifact_ref_v1(prev_root_tuple.get("wroot"))
                init_wroot_id, init_weights = _load_weights_manifest_from_repo(wroot_ref=init_wroot_ref, base_repo_root=base)

        # Replay training to obtain final WRoot and H_train tail.
        final_bytes_exp, final_id_exp, final_obj_exp, final_blocks_exp, h_train_tail32, _dbg = replay_qxrl_training_v1(
            training_manifest_obj=training_obj,
            model=model,
            dataset_root_hash32=dataset_root_hash32,
            examples=examples,
            initial_weights_manifest_id=init_wroot_id,
            initial_weights_manifest=init_weights,
            registry_loader=registry_loader,
            return_debug=False,
        )
        if digest32_to_hex(h_train_tail32) != h_train_tail32_hex:
            return False, REASON_QXRL_TRAIN_TAIL_MISMATCH
        if str(final_id_exp).strip() != str(final_wroot_id).strip():
            return False, REASON_QXRL_TRAIN_TAIL_MISMATCH

        # Require final weights manifest bytes match exactly.
        final_bytes_actual = bytes(registry_loader(wroot_ref))
        if bytes(final_bytes_actual) != bytes(final_bytes_exp):
            return False, REASON_QXRL_TRAIN_TAIL_MISMATCH

        # Replay evaluation deterministically using final weights.
        scorecard_ref = require_artifact_ref_v1(eval_obj.get("scorecard_ref"))
        scorecard_bytes_actual = bytes(registry_loader(scorecard_ref))
        scorecard_obj_actual = gcj1_loads_and_verify_canonical(scorecard_bytes_actual)
        if not isinstance(scorecard_obj_actual, dict):
            return False, REASON_QXRL_SCHEMA_INVALID
        require_no_absolute_paths(scorecard_obj_actual)
        _validate_schema(dict(scorecard_obj_actual), SCHEMA_QXRL_EVAL_SCORECARD_V1, reason=REASON_QXRL_SCHEMA_INVALID)

        try:
            scorecard_obj_exp, scorecard_bytes_exp, scorecard_artifact_id_exp, h_eval_tail32 = compute_qxrl_eval_scorecard_v1(
                eval_manifest_obj=eval_obj,
                model=model,
                model_manifest_id=str(model_ref.get("artifact_id", "")).strip(),
                dataset_manifest_obj=dataset_obj,
                dataset_root_hash32=dataset_root_hash32,
                examples=examples,
                weights_manifest_id=str(final_wroot_id).strip(),
                weights_manifest=final_weights,
                registry_loader=registry_loader,
                enforce_floors=True,
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if REASON_QXRL_FLOOR_FAIL in msg:
                return False, REASON_QXRL_FLOOR_FAIL
            return False, REASON_QXRL_SCHEMA_INVALID

        if str(scorecard_ref.get("artifact_id", "")).strip() != str(scorecard_artifact_id_exp).strip():
            return False, REASON_QXRL_SCORECARD_MISMATCH
        if bytes(scorecard_bytes_actual) != bytes(scorecard_bytes_exp):
            return False, REASON_QXRL_SCORECARD_MISMATCH

        if digest32_to_hex(h_eval_tail32) != h_eval_tail32_hex:
            return False, REASON_QXRL_EVAL_TAIL_MISMATCH

        return True, EUDRSU_OK
    except Exception:
        # Fail-closed: map any unexpected runtime to schema invalid.
        return False, REASON_QXRL_SCHEMA_INVALID


__all__ = ["verify_qxrl_v1"]
