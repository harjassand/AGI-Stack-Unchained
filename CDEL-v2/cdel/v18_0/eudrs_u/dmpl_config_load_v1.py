"""DMPL config/runtime loader (v1).

Phase 2 contract:
  - Load DMPL artifacts from droot/config/modelpack/params bundles.
  - Verify caps cross-checks and params bundle merkle roots.
  - Load required base tensors into deterministic Python containers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..omega_common_v1 import OmegaV18Error, fail, require_no_absolute_paths, validate_schema
from .dmpl_merkle_v1 import compute_params_bundle_merkle_root_v1
from .dmpl_tensor_io_v1 import parse_tensor_q32_v1, require_shape
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_DIM_MISMATCH,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_NONCANON_GCJ1,
    DMPL_E_OPSET_MISMATCH,
    _sha25632_count,
    _sha256_id_from_hex_digest32,
    _sha256_id_to_digest32,
)
from .eudrs_u_hash_v1 import artifact_id_from_json_obj, gcj1_loads_and_verify_canonical


def _resolver_load_bytes(resolver: Any, *, artifact_id: str, artifact_type: str, ext: str) -> bytes:
    # Resolver interface (Phase 2): resolver.load_artifact_bytes(artifact_id, artifact_type, ext)->bytes
    try:
        fn = getattr(resolver, "load_artifact_bytes")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing load_artifact_bytes"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver.load_artifact_bytes not callable"})
    raw = fn(artifact_id=str(artifact_id), artifact_type=str(artifact_type), ext=str(ext))
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
    return bytes(raw)


def _load_json_artifact(*, resolver: Any, artifact_id: str, artifact_type: str) -> dict[str, Any]:
    raw = _resolver_load_bytes(resolver, artifact_id=str(artifact_id), artifact_type=str(artifact_type), ext="json")
    if _sha256_id_from_hex_digest32(_sha25632_count(raw)) != str(artifact_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    try:
        obj = gcj1_loads_and_verify_canonical(raw)
    except OmegaV18Error:
        raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    if not isinstance(obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"artifact_type": str(artifact_type), "hint": "not dict"})
    require_no_absolute_paths(obj)
    try:
        validate_schema(obj, str(artifact_type))
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"artifact_type": str(artifact_type), "artifact_id": str(artifact_id)})
    return dict(obj)


def _load_bin_artifact(*, resolver: Any, artifact_id: str, artifact_type: str) -> bytes:
    raw = _resolver_load_bytes(resolver, artifact_id=str(artifact_id), artifact_type=str(artifact_type), ext="bin")
    if _sha256_id_from_hex_digest32(_sha25632_count(raw)) != str(artifact_id).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(artifact_id), "artifact_type": str(artifact_type)})
    return bytes(raw)


@dataclass(frozen=True, slots=True)
class DmplDims:
    d_u32: int
    p_u32: int
    embed_dim_u32: int


@dataclass(frozen=True, slots=True)
class DmplRuntime:
    dc1_id: str
    opset_id: str
    droot_id: str
    caps: dict
    config: dict
    modelpack: dict
    dims: DmplDims
    base_forward: dict[str, tuple[list[int], list[int]]]
    base_value: dict[str, tuple[list[int], list[int]]]
    modelpack_hash32: bytes
    caps_digest: str


def _require_u32(value: Any, *, reason: str) -> int:
    if not isinstance(value, int) or value < 0 or value > 0xFFFFFFFF:
        raise DMPLError(reason_code=reason, details={"value": value})
    return int(value)


def _require_sha256_id(value: Any, *, reason: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != (len("sha256:") + 64):
        raise DMPLError(reason_code=reason, details={"value": str(value)})
    # hex validation
    _sha256_id_to_digest32(str(value), reason=reason)
    return str(value)


def _index_tensors_by_name(bundle_obj: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tensors_raw = bundle_obj.get("tensors")
    if not isinstance(tensors_raw, list) or not tensors_raw:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bundle tensors missing"})
    prev: str | None = None
    out: dict[str, dict[str, Any]] = {}
    for row in tensors_raw:
        if not isinstance(row, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "tensor row type"})
        name = row.get("name")
        if not isinstance(name, str) or not name:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "tensor name"})
        if prev is not None and str(name) <= prev:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "tensor order"})
        prev = str(name)
        if str(name) in out:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "tensor dup", "name": str(name)})
        out[str(name)] = dict(row)
    return out


def _load_required_tensor(
    *,
    resolver: Any,
    tensor_row: dict[str, Any],
    expected_name: str,
    expected_shape: list[int],
) -> tuple[list[int], list[int]]:
    if str(tensor_row.get("name", "")).strip() != str(expected_name):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "tensor name mismatch", "name": str(tensor_row.get("name", ""))})
    shape = tensor_row.get("shape_u32")
    if not isinstance(shape, list):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "shape missing"})
    declared: list[int] = []
    for dim in shape:
        declared.append(_require_u32(dim, reason=DMPL_E_DIM_MISMATCH))
    require_shape(declared, [int(x) for x in expected_shape])

    tensor_bin_id = _require_sha256_id(tensor_row.get("tensor_bin_id"), reason=DMPL_E_OPSET_MISMATCH)
    raw = _load_bin_artifact(resolver=resolver, artifact_id=tensor_bin_id, artifact_type="dmpl_tensor_q32_v1")
    dims, values = parse_tensor_q32_v1(raw)
    require_shape(dims, declared)
    return dims, values


def load_runtime_from_droot_v1(droot_id: str, resolver) -> DmplRuntime:
    droot_id = _require_sha256_id(droot_id, reason=DMPL_E_OPSET_MISMATCH)
    droot = _load_json_artifact(resolver=resolver, artifact_id=droot_id, artifact_type="dmpl_droot_v1")

    dc1_id = str(droot.get("dc1_id", "")).strip()
    opset_id = str(droot.get("opset_id", "")).strip()
    if dc1_id != "dc1:q32_v1" or not opset_id.startswith("opset:eudrs_u_v1:sha256:"):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "droot ids"})

    config_id = _require_sha256_id(droot.get("dmpl_config_id"), reason=DMPL_E_OPSET_MISMATCH)
    config = _load_json_artifact(resolver=resolver, artifact_id=config_id, artifact_type="dmpl_config_v1")
    if str(config.get("dc1_id", "")).strip() != dc1_id or str(config.get("opset_id", "")).strip() != opset_id:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "config ids"})

    caps = config.get("caps")
    if not isinstance(caps, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "caps type"})
    caps_digest_exp = artifact_id_from_json_obj(caps)
    if str(caps_digest_exp).strip() != str(droot.get("caps_digest", "")).strip():
        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "caps digest"})

    retrieval_spec = config.get("retrieval_spec")
    if not isinstance(retrieval_spec, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "retrieval_spec type"})
    if int(retrieval_spec.get("K_ctx_u32", -1)) != int(caps.get("K_ctx_u32", -2)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "K_ctx mismatch"})

    modelpack_id = _require_sha256_id(config.get("active_modelpack_id"), reason=DMPL_E_OPSET_MISMATCH)
    modelpack = _load_json_artifact(resolver=resolver, artifact_id=modelpack_id, artifact_type="dmpl_modelpack_v1")
    if str(modelpack.get("dc1_id", "")).strip() != dc1_id or str(modelpack.get("opset_id", "")).strip() != opset_id:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "modelpack ids"})

    dims_obj = modelpack.get("dims")
    if not isinstance(dims_obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "dims type"})
    dims = DmplDims(
        d_u32=_require_u32(dims_obj.get("d_u32"), reason=DMPL_E_OPSET_MISMATCH),
        p_u32=_require_u32(dims_obj.get("p_u32"), reason=DMPL_E_OPSET_MISMATCH),
        embed_dim_u32=_require_u32(dims_obj.get("embed_dim_u32"), reason=DMPL_E_OPSET_MISMATCH),
    )

    # Load and verify params bundles + bind froot/vroot.
    fparams_id = _require_sha256_id(config.get("fparams_bundle_id"), reason=DMPL_E_OPSET_MISMATCH)
    vparams_id = _require_sha256_id(config.get("vparams_bundle_id"), reason=DMPL_E_OPSET_MISMATCH)

    base_forward: dict[str, tuple[list[int], list[int]]] = {}
    base_value: dict[str, tuple[list[int], list[int]]] = {}

    required_forward = {"A0", "B0", "b0", "Wg"}
    required_value = {"v0", "w0"}

    for bundle_kind, bundle_id, expected_root_key in (("F", fparams_id, "froot"), ("V", vparams_id, "vroot")):
        bundle = _load_json_artifact(resolver=resolver, artifact_id=bundle_id, artifact_type="dmpl_params_bundle_v1")
        if str(bundle.get("dc1_id", "")).strip() != dc1_id or str(bundle.get("opset_id", "")).strip() != opset_id:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bundle ids"})
        if str(bundle.get("bundle_kind", "")).strip() != bundle_kind:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bundle kind"})
        if str(bundle.get("modelpack_id", "")).strip() != modelpack_id:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bundle modelpack"})

        merkle_root_exp = compute_params_bundle_merkle_root_v1(bundle_obj=bundle, resolver=resolver)
        if str(merkle_root_exp).strip() != str(bundle.get("merkle_root", "")).strip():
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "bundle merkle_root"})
        if str(merkle_root_exp).strip() != str(droot.get(expected_root_key, "")).strip():
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "droot root bind"})

        indexed = _index_tensors_by_name(bundle)
        names = set(indexed.keys())
        if bundle_kind == "F":
            missing = sorted(required_forward - names)
            if missing:
                raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"missing": missing})
            extra = sorted(names - required_forward)
            if extra:
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"extra": extra})

            base_forward["A0"] = _load_required_tensor(resolver=resolver, tensor_row=indexed["A0"], expected_name="A0", expected_shape=[dims.d_u32, dims.d_u32])
            base_forward["B0"] = _load_required_tensor(resolver=resolver, tensor_row=indexed["B0"], expected_name="B0", expected_shape=[dims.d_u32, dims.p_u32])
            base_forward["b0"] = _load_required_tensor(resolver=resolver, tensor_row=indexed["b0"], expected_name="b0", expected_shape=[dims.d_u32])
            base_forward["Wg"] = _load_required_tensor(
                resolver=resolver,
                tensor_row=indexed["Wg"],
                expected_name="Wg",
                expected_shape=[dims.embed_dim_u32, dims.d_u32],
            )
        else:
            missing = sorted(required_value - names)
            if missing:
                raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"missing": missing})
            extra = sorted(names - required_value)
            if extra:
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"extra": extra})

            base_value["w0"] = _load_required_tensor(resolver=resolver, tensor_row=indexed["w0"], expected_name="w0", expected_shape=[dims.d_u32])
            base_value["v0"] = _load_required_tensor(resolver=resolver, tensor_row=indexed["v0"], expected_name="v0", expected_shape=[1])

    modelpack_hash32 = _sha256_id_to_digest32(modelpack_id, reason=DMPL_E_OPSET_MISMATCH)

    return DmplRuntime(
        dc1_id=dc1_id,
        opset_id=opset_id,
        droot_id=droot_id,
        caps=dict(caps),
        config=dict(config),
        modelpack=dict(modelpack),
        dims=dims,
        base_forward=base_forward,
        base_value=base_value,
        modelpack_hash32=bytes(modelpack_hash32),
        caps_digest=str(droot.get("caps_digest", "")).strip(),
    )


__all__ = [
    "DmplDims",
    "DmplRuntime",
    "load_runtime_from_droot_v1",
]
