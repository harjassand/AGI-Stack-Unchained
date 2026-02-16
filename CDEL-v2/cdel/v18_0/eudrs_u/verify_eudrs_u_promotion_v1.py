"""Fail-closed verifier for EUDRS-U promotion outputs (v1).

Entry point for subverification: validate the producer-emitted promotion summary,
content-addressed evidence artifacts, and staged registry tree (including root
tuple + activation pointer).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import struct
from pathlib import Path
from typing import Any

from ..omega_common_v1 import OmegaV18Error, fail, repo_root, require_no_absolute_paths, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, require_safe_relpath_v1, verify_artifact_ref_v1
from .eudrs_u_common_v1 import (
    EUDRS_U_ACTIVE_POINTER_REL,
    EUDRS_U_EVIDENCE_DIR_REL,
    SCHEMA_ACTIVE_ROOT_TUPLE_REF_V1,
    SCHEMA_EUDRS_U_PROMOTION_SUMMARY_V1,
    SCHEMA_EUDRS_U_ROOT_TUPLE_V1,
    SCHEMA_EUDRS_U_SYSTEM_MANIFEST_V1,
    load_active_root_tuple_pointer,
)
from .eudrs_u_hash_v1 import artifact_id_from_json_obj, gcj1_loads_and_verify_canonical, sha256_file_stream, sha256_prefixed
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_DISABLED,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_NONCANON_GCJ1,
    DMPL_E_OPSET_MISMATCH,
)
from .ml_index_v1 import (
    decode_ml_index_codebook_v1,
    decode_ml_index_root_v1,
    load_ml_index_pages_by_bucket_v1,
    require_ml_index_bucket_listing_v1,
    require_ml_index_manifest_v1,
    verify_ml_index_merkle_roots_v1,
)
from .mem_gates_v1 import verify_mem_gates_v1
from .verify_dmpl_opset_v1 import verify_dmpl_opset_v1
from .verify_dmpl_plan_replay_v1 import verify_dmpl_plan_replay_v1
from .verify_dmpl_train_replay_v1 import verify_dmpl_train_replay_v1
from .verify_dmpl_certificates_v1 import verify_dmpl_certificates_gated_v1

_OPSET_ID_RE = re.compile(r"^opset:eudrs_u_v1:sha256:[0-9a-f]{64}$")
_SHA256_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_DMPL_REGISTRY_PREFIX = "polymath/registry/eudrs_u/"

_DMPL_MERKLE_LEAF_PREFIX = b"DMPL/MERKLE/LEAF/v1\x00"
_DMPL_MERKLE_NODE_PREFIX = b"DMPL/MERKLE/NODE/v1\x00"

_DMPL_TENSOR_MAGIC = b"DMPLTQ32"


def _validate_schema(obj: dict[str, Any], schema_name: str) -> None:
    try:
        validate_schema(obj, schema_name)
    except Exception:  # noqa: BLE001 - fail-closed on any validator/runtime error
        fail("SCHEMA_FAIL")


def _resolve_state_dir(path: Path) -> Path:
    root = Path(path).resolve()
    if (root / EUDRS_U_EVIDENCE_DIR_REL).is_dir():
        return root

    daemon_dir = root / "daemon"
    if daemon_dir.exists() and daemon_dir.is_dir():
        for candidate in sorted(daemon_dir.glob("*/state"), key=lambda row: row.as_posix()):
            if (candidate / EUDRS_U_EVIDENCE_DIR_REL).is_dir():
                return candidate.resolve()

    fail("SCHEMA_FAIL")
    return root


def _load_single_summary(evidence_dir: Path) -> tuple[Path, dict[str, Any]]:
    # Producer MUST emit exactly one summary object under eudrs_u/evidence/.
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(evidence_dir.glob("*.json"), key=lambda row: row.as_posix()):
        payload = gcj1_loads_and_verify_canonical(path.read_bytes())
        if not isinstance(payload, dict):
            continue
        if str(payload.get("schema_id", "")).strip() == SCHEMA_EUDRS_U_PROMOTION_SUMMARY_V1:
            matches.append((path, dict(payload)))

    if len(matches) != 1:
        fail("SCHEMA_FAIL")
    summary_path, payload = matches[0]
    _validate_schema(payload, SCHEMA_EUDRS_U_PROMOTION_SUMMARY_V1)
    return summary_path, payload


def _verify_staged_active_pointer(
    *,
    staged_root: Path,
    expected_root_tuple_ref: dict[str, str],
) -> None:
    pointer_path = staged_root / EUDRS_U_ACTIVE_POINTER_REL
    if not pointer_path.exists() or not pointer_path.is_file():
        fail("MISSING_STATE_INPUT")
    payload = gcj1_loads_and_verify_canonical(pointer_path.read_bytes())
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if str(payload.get("schema_id", "")).strip() != SCHEMA_ACTIVE_ROOT_TUPLE_REF_V1:
        fail("SCHEMA_FAIL")
    active = payload.get("active_root_tuple")
    active_ref = require_artifact_ref_v1(active)
    if active_ref != expected_root_tuple_ref:
        fail("NONDETERMINISTIC")


def _load_root_tuple_epoch(root_tuple: dict[str, Any]) -> int:
    epoch = root_tuple.get("epoch_u64")
    if not isinstance(epoch, int) or epoch < 0:
        fail("SCHEMA_FAIL")
    return int(epoch)


def _verify_root_tuple_epoch(
    *,
    new_root_tuple: dict[str, Any],
    repo_root_override: Path | None,
    enforce_increment: bool,
) -> None:
    new_epoch = _load_root_tuple_epoch(new_root_tuple)
    if not bool(enforce_increment):
        return

    base = repo_root() if repo_root_override is None else Path(repo_root_override).resolve()
    pointer_payload = load_active_root_tuple_pointer(root=base)
    if pointer_payload is None:
        if new_epoch != 0:
            fail("NONDETERMINISTIC")
        return

    if str(pointer_payload.get("schema_id", "")).strip() != SCHEMA_ACTIVE_ROOT_TUPLE_REF_V1:
        fail("SCHEMA_FAIL")
    active_ref = require_artifact_ref_v1(pointer_payload.get("active_root_tuple"))

    # Verify previous root tuple exists and is content-addressed in the repo.
    active_path = verify_artifact_ref_v1(artifact_ref=active_ref, base_dir=base)
    prev_root_tuple = gcj1_loads_and_verify_canonical(active_path.read_bytes())
    if not isinstance(prev_root_tuple, dict):
        fail("SCHEMA_FAIL")
    _validate_schema(prev_root_tuple, SCHEMA_EUDRS_U_ROOT_TUPLE_V1)
    prev_epoch = _load_root_tuple_epoch(dict(prev_root_tuple))

    if new_epoch != prev_epoch + 1:
        fail("NONDETERMINISTIC")


def _verify_root_tuple_fields(root_tuple: dict[str, Any]) -> None:
    _validate_schema(root_tuple, SCHEMA_EUDRS_U_ROOT_TUPLE_V1)

    dc1_id = str(root_tuple.get("dc1_id", "")).strip()
    if dc1_id != "dc1:q32_v1":
        fail("SCHEMA_FAIL")

    opset_id = str(root_tuple.get("opset_id", "")).strip()
    if _OPSET_ID_RE.fullmatch(opset_id) is None:
        fail("SCHEMA_FAIL")


def _verify_artifact_refs_in_root_tuple(*, root_tuple: dict[str, Any], staged_root: Path) -> None:
    expected_dc1_id = str(root_tuple.get("dc1_id", "")).strip()
    expected_opset_id = str(root_tuple.get("opset_id", "")).strip()
    required = [
        "sroot",
        "oroot",
        "kroot",
        "croot",
        "droot",
        "mroot",
        "iroot",
        "wroot",
        "stability_gate_bundle",
        "determinism_cert",
        "universality_cert",
    ]
    for key in required:
        ref_raw = root_tuple.get(key)
        ref = require_artifact_ref_v1(ref_raw)
        path = verify_artifact_ref_v1(artifact_ref=ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/")
        if path.name.endswith(".json"):
            payload = gcj1_loads_and_verify_canonical(path.read_bytes())
            if not isinstance(payload, dict):
                fail("SCHEMA_FAIL")
            require_no_absolute_paths(payload)
            dc1_id = str(payload.get("dc1_id", "")).strip()
            opset_id = str(payload.get("opset_id", "")).strip()
            if not dc1_id or not opset_id:
                fail("SCHEMA_FAIL")
            if dc1_id != expected_dc1_id or opset_id != expected_opset_id:
                fail("NONDETERMINISTIC")


def _sha256_id_to_hex64(value: Any) -> str:
    if not isinstance(value, str) or _SHA256_ID_RE.fullmatch(value) is None:
        fail("SCHEMA_FAIL")
    return value.split(":", 1)[1]


def _sha256_id_to_digest32(value: Any) -> bytes:
    hex64 = _sha256_id_to_hex64(value)
    try:
        raw = bytes.fromhex(hex64)
    except Exception:
        fail("SCHEMA_FAIL")
    if len(raw) != 32:
        fail("SCHEMA_FAIL")
    return raw


def _find_unique_artifact_path_by_id_and_type(
    *,
    base_dir: Path,
    expected_relpath_prefix: str,
    artifact_id: str,
    artifact_type: str,
    ext: str,
) -> Path:
    if ext not in {"json", "bin"}:
        fail("SCHEMA_FAIL")
    hex64 = _sha256_id_to_hex64(artifact_id)
    filename = f"sha256_{hex64}.{artifact_type}.{ext}"

    base_abs = Path(base_dir).resolve()
    prefix_dir = (base_abs / expected_relpath_prefix).resolve()
    try:
        prefix_dir.relative_to(base_abs)
    except Exception:
        fail("SCHEMA_FAIL")
    if not prefix_dir.exists() or not prefix_dir.is_dir():
        fail("MISSING_STATE_INPUT")

    matches = [p for p in prefix_dir.rglob(filename) if p.is_file()]
    matches = sorted(matches, key=lambda row: row.as_posix())
    if not matches:
        fail("MISSING_STATE_INPUT")
    if len(matches) != 1:
        fail("SCHEMA_FAIL")
    return matches[0]


def _load_json_artifact_by_id_and_type(
    *,
    base_dir: Path,
    expected_relpath_prefix: str,
    artifact_id: str,
    artifact_type: str,
) -> dict[str, Any]:
    path = _find_unique_artifact_path_by_id_and_type(
        base_dir=base_dir,
        expected_relpath_prefix=expected_relpath_prefix,
        artifact_id=str(artifact_id),
        artifact_type=str(artifact_type),
        ext="json",
    )
    raw = path.read_bytes()
    payload = gcj1_loads_and_verify_canonical(raw)
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(payload)
    if sha256_prefixed(raw) != str(artifact_id).strip():
        fail("NONDETERMINISTIC")
    return dict(payload)


class _DMPLPromotionResolverV1:
    """Resolver for DMPL replay verifiers (promotion verification context)."""

    def __init__(self, *, state_root: Path, evidence_dir: Path, staged_registry_tree_abs: Path) -> None:
        self._state_root = Path(state_root).resolve()
        self._roots = [
            Path(evidence_dir).resolve(),
            Path(staged_registry_tree_abs).resolve(),
        ]

    def load_artifact_bytes(self, *, artifact_id: str, artifact_type: str, ext: str) -> bytes:
        aid = str(artifact_id).strip()
        at = str(artifact_type).strip()
        ex = str(ext).strip()
        if _SHA256_ID_RE.fullmatch(aid) is None:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"artifact_id": str(aid)})
        if not at or ex not in {"json", "bin"}:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bad resolver request"})
        hex64 = aid.split(":", 1)[1]
        filename = f"sha256_{hex64}.{at}.{ex}"

        matches: list[Path] = []
        for root in self._roots:
            if not root.exists() or not root.is_dir():
                continue
            matches.extend([p for p in root.rglob(filename) if p.is_file()])
        matches = sorted(matches, key=lambda p: p.as_posix())
        if not matches:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "resolver lookup", "filename": filename, "matches": 0})

        # Allow duplicates across roots as long as bytes are identical (content-addressed);
        # tie-break deterministically by choosing the lexicographically smallest path.
        raw0 = matches[0].read_bytes()
        if sha256_prefixed(raw0) != aid:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "resolver hash mismatch", "artifact_id": aid})
        for path in matches[1:]:
            raw_i = path.read_bytes()
            if sha256_prefixed(raw_i) != aid:
                raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "resolver hash mismatch", "artifact_id": aid})
            if raw_i != raw0:
                raise DMPLError(
                    reason_code=DMPL_E_HASH_MISMATCH,
                    details={"hint": "resolver duplicate mismatch", "artifact_id": aid, "filename": filename, "matches": int(len(matches))},
                )
        return raw0

    def load_artifact_ref_bytes(self, artifact_ref: dict[str, Any], *, expected_relpath_prefix: str | None = None) -> bytes:
        try:
            path = verify_artifact_ref_v1(
                artifact_ref=require_artifact_ref_v1(artifact_ref),
                base_dir=self._state_root,
                expected_relpath_prefix=expected_relpath_prefix,
            )
        except OmegaV18Error:
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "bad ArtifactRef"})
        return path.read_bytes()


def _verify_and_load_dmpl_tensor_bin_v1(*, staged_root: Path, tensor_bin_id: str, shape_u32: list[int]) -> None:
    path = _find_unique_artifact_path_by_id_and_type(
        base_dir=staged_root,
        expected_relpath_prefix=_DMPL_REGISTRY_PREFIX,
        artifact_id=str(tensor_bin_id),
        artifact_type="dmpl_tensor_q32_v1",
        ext="bin",
    )

    digest = sha256_file_stream(path)
    if str(digest).strip() != str(tensor_bin_id).strip():
        fail("DMPL_E_HASH_MISMATCH")

    # Parse header and verify shape.
    size = int(path.stat().st_size)
    with path.open("rb") as handle:
        header16 = handle.read(16)
        if len(header16) != 16:
            fail("DMPL_E_DIM_MISMATCH")
        magic = header16[0:8]
        if magic != _DMPL_TENSOR_MAGIC:
            fail("SCHEMA_FAIL")
        version_u32, ndim_u32 = struct.unpack("<II", header16[8:16])
        if int(version_u32) != 1:
            fail("SCHEMA_FAIL")
        ndim = int(ndim_u32)
        if ndim != len(shape_u32):
            fail("DMPL_E_DIM_MISMATCH")
        dims: list[int] = []
        prod = 1
        for _i in range(ndim):
            b4 = handle.read(4)
            if len(b4) != 4:
                fail("DMPL_E_DIM_MISMATCH")
            dim = int(struct.unpack("<I", b4)[0])
            dims.append(dim)
            prod *= dim
        if [int(v) for v in dims] != [int(v) for v in shape_u32]:
            fail("DMPL_E_DIM_MISMATCH")
        expected_size = 16 + (4 * ndim) + (prod * 8)
        if int(expected_size) != int(size):
            fail("DMPL_E_DIM_MISMATCH")


def _compute_dmpl_params_bundle_merkle_root_v1(*, tensors: list[dict[str, Any]]) -> str:
    # Deterministic ordering: tensors[] sorted by name asc, strictly increasing.
    leaf_hashes: list[bytes] = []
    prev_name: str | None = None
    for row in tensors:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        name = row.get("name")
        if not isinstance(name, str) or not name:
            fail("SCHEMA_FAIL")
        if "\x00" in name:
            fail("SCHEMA_FAIL")
        if prev_name is not None and name <= prev_name:
            fail("SCHEMA_FAIL")
        prev_name = name
        name_bytes = name.encode("utf-8", errors="strict")
        tensor_digest32 = _sha256_id_to_digest32(row.get("tensor_bin_id"))
        leaf = hashlib.sha256(_DMPL_MERKLE_LEAF_PREFIX + name_bytes + b"\x00" + tensor_digest32).digest()
        if len(leaf) != 32:
            fail("SCHEMA_FAIL")
        leaf_hashes.append(leaf)

    if not leaf_hashes:
        fail("SCHEMA_FAIL")

    level = list(leaf_hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level = level + [level[-1]]
        nxt: list[bytes] = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1]
            nxt.append(hashlib.sha256(_DMPL_MERKLE_NODE_PREFIX + left + right).digest())
        level = nxt

    root32 = level[0]
    if not isinstance(root32, (bytes, bytearray, memoryview)) or len(bytes(root32)) != 32:
        fail("SCHEMA_FAIL")
    return f"sha256:{bytes(root32).hex()}"


def _verify_dmpl_droot_phase1(*, root_tuple: dict[str, Any], staged_root: Path) -> None:
    expected_dc1_id = str(root_tuple.get("dc1_id", "")).strip()
    expected_opset_id = str(root_tuple.get("opset_id", "")).strip()

    droot_ref = require_artifact_ref_v1(root_tuple.get("droot"))
    droot_path = verify_artifact_ref_v1(
        artifact_ref=droot_ref,
        base_dir=staged_root,
        expected_relpath_prefix=_DMPL_REGISTRY_PREFIX,
    )
    droot_bytes = droot_path.read_bytes()
    droot_obj = gcj1_loads_and_verify_canonical(droot_bytes)
    if not isinstance(droot_obj, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(droot_obj)
    _validate_schema(droot_obj, "dmpl_droot_v1")

    if str(droot_obj.get("dc1_id", "")).strip() != expected_dc1_id:
        fail("NONDETERMINISTIC")
    if str(droot_obj.get("opset_id", "")).strip() != expected_opset_id:
        fail("NONDETERMINISTIC")
    if str(droot_obj.get("opset_semantics_id", "")).strip() != expected_opset_id:
        fail("NONDETERMINISTIC")

    dmpl_config_id = str(droot_obj.get("dmpl_config_id", "")).strip()
    config_obj = _load_json_artifact_by_id_and_type(
        base_dir=staged_root,
        expected_relpath_prefix=_DMPL_REGISTRY_PREFIX,
        artifact_id=dmpl_config_id,
        artifact_type="dmpl_config_v1",
    )
    _validate_schema(config_obj, "dmpl_config_v1")

    if str(config_obj.get("dc1_id", "")).strip() != expected_dc1_id:
        fail("NONDETERMINISTIC")
    if str(config_obj.get("opset_id", "")).strip() != expected_opset_id:
        fail("NONDETERMINISTIC")

    # Bind caps_digest.
    caps_obj = config_obj.get("caps")
    if not isinstance(caps_obj, dict):
        fail("SCHEMA_FAIL")
    caps_digest_exp = artifact_id_from_json_obj(caps_obj)
    if str(caps_digest_exp).strip() != str(droot_obj.get("caps_digest", "")).strip():
        fail("NONDETERMINISTIC")

    # Load and validate modelpack.
    modelpack_id = str(config_obj.get("active_modelpack_id", "")).strip()
    modelpack_obj = _load_json_artifact_by_id_and_type(
        base_dir=staged_root,
        expected_relpath_prefix=_DMPL_REGISTRY_PREFIX,
        artifact_id=modelpack_id,
        artifact_type="dmpl_modelpack_v1",
    )
    _validate_schema(modelpack_obj, "dmpl_modelpack_v1")
    if str(modelpack_obj.get("dc1_id", "")).strip() != expected_dc1_id:
        fail("NONDETERMINISTIC")
    if str(modelpack_obj.get("opset_id", "")).strip() != expected_opset_id:
        fail("NONDETERMINISTIC")

    # Enforce duplicated audit fields.
    retrieval_spec = config_obj.get("retrieval_spec")
    if not isinstance(retrieval_spec, dict):
        fail("SCHEMA_FAIL")
    retrieval_k_ctx = retrieval_spec.get("K_ctx_u32")
    caps_k_ctx = caps_obj.get("K_ctx_u32")
    if not isinstance(retrieval_k_ctx, int) or not isinstance(caps_k_ctx, int):
        fail("SCHEMA_FAIL")
    if int(retrieval_k_ctx) != int(caps_k_ctx):
        fail("NONDETERMINISTIC")

    # Load and validate forward/value params bundles; recompute and bind froot/vroot.
    fparams_id = str(config_obj.get("fparams_bundle_id", "")).strip()
    vparams_id = str(config_obj.get("vparams_bundle_id", "")).strip()
    for kind, bundle_id, expected_root_key in (("F", fparams_id, "froot"), ("V", vparams_id, "vroot")):
        bundle_obj = _load_json_artifact_by_id_and_type(
            base_dir=staged_root,
            expected_relpath_prefix=_DMPL_REGISTRY_PREFIX,
            artifact_id=bundle_id,
            artifact_type="dmpl_params_bundle_v1",
        )
        _validate_schema(bundle_obj, "dmpl_params_bundle_v1")
        if str(bundle_obj.get("dc1_id", "")).strip() != expected_dc1_id:
            fail("NONDETERMINISTIC")
        if str(bundle_obj.get("opset_id", "")).strip() != expected_opset_id:
            fail("NONDETERMINISTIC")
        if str(bundle_obj.get("bundle_kind", "")).strip() != kind:
            fail("SCHEMA_FAIL")
        if str(bundle_obj.get("modelpack_id", "")).strip() != modelpack_id:
            fail("NONDETERMINISTIC")

        tensors_raw = bundle_obj.get("tensors")
        if not isinstance(tensors_raw, list):
            fail("SCHEMA_FAIL")
        tensors: list[dict[str, Any]] = []
        for row in tensors_raw:
            if not isinstance(row, dict):
                fail("SCHEMA_FAIL")
            tensors.append(dict(row))

        # Verify each referenced tensor binary exists and matches the declared shape.
        for tensor in tensors:
            shape = tensor.get("shape_u32")
            if not isinstance(shape, list):
                fail("SCHEMA_FAIL")
            shape_u32: list[int] = []
            for dim in shape:
                if not isinstance(dim, int) or dim < 0 or dim > 0xFFFFFFFF:
                    fail("SCHEMA_FAIL")
                shape_u32.append(int(dim))
            tensor_bin_id = str(tensor.get("tensor_bin_id", "")).strip()
            _verify_and_load_dmpl_tensor_bin_v1(staged_root=staged_root, tensor_bin_id=tensor_bin_id, shape_u32=shape_u32)

        merkle_root_exp = _compute_dmpl_params_bundle_merkle_root_v1(tensors=tensors)
        if str(merkle_root_exp).strip() != str(bundle_obj.get("merkle_root", "")).strip():
            fail("NONDETERMINISTIC")
        if str(merkle_root_exp).strip() != str(droot_obj.get(expected_root_key, "")).strip():
            fail("NONDETERMINISTIC")


def _verify_sroot_system_manifest_binding(*, root_tuple: dict[str, Any], staged_root: Path) -> None:
    """Phase-1 hard requirement: sroot must bind the system manifest."""

    epoch_u64 = root_tuple.get("epoch_u64")
    if not isinstance(epoch_u64, int) or epoch_u64 < 0:
        fail("SCHEMA_FAIL")

    expected_dc1_id = str(root_tuple.get("dc1_id", "")).strip()
    expected_opset_id = str(root_tuple.get("opset_id", "")).strip()
    sroot_ref = require_artifact_ref_v1(root_tuple.get("sroot"))

    sroot_path = verify_artifact_ref_v1(
        artifact_ref=sroot_ref,
        base_dir=staged_root,
        expected_relpath_prefix="polymath/registry/eudrs_u/",
    )
    payload = gcj1_loads_and_verify_canonical(sroot_path.read_bytes())
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(payload)

    if str(payload.get("schema_id", "")).strip() != SCHEMA_EUDRS_U_SYSTEM_MANIFEST_V1:
        fail("SCHEMA_FAIL")

    # Validate schema (when available) and enforce required bindings.
    _validate_schema(payload, SCHEMA_EUDRS_U_SYSTEM_MANIFEST_V1)

    if payload.get("epoch_u64") != epoch_u64:
        fail("NONDETERMINISTIC")
    if str(payload.get("dc1_id", "")).strip() != expected_dc1_id:
        fail("NONDETERMINISTIC")
    if str(payload.get("opset_id", "")).strip() != expected_opset_id:
        fail("NONDETERMINISTIC")


def _load_prev_active_root_tuple(*, repo_root_override: Path | None) -> dict[str, Any] | None:
    base = repo_root() if repo_root_override is None else Path(repo_root_override).resolve()
    pointer_payload = load_active_root_tuple_pointer(root=base)
    if pointer_payload is None:
        return None
    if str(pointer_payload.get("schema_id", "")).strip() != SCHEMA_ACTIVE_ROOT_TUPLE_REF_V1:
        fail("SCHEMA_FAIL")
    active_ref = require_artifact_ref_v1(pointer_payload.get("active_root_tuple"))
    active_path = verify_artifact_ref_v1(artifact_ref=active_ref, base_dir=base)
    prev_root_tuple = gcj1_loads_and_verify_canonical(active_path.read_bytes())
    if not isinstance(prev_root_tuple, dict):
        fail("SCHEMA_FAIL")
    _validate_schema(prev_root_tuple, SCHEMA_EUDRS_U_ROOT_TUPLE_V1)
    return dict(prev_root_tuple)


def _verify_ml_index_if_changed(
    *,
    summary: dict[str, Any],
    new_root_tuple: dict[str, Any],
    state_root: Path,
    staged_registry_tree_abs: Path,
    repo_root_override: Path | None,
) -> None:
    """Verify ML-Index bundle + MEM gates if the index root changes."""

    prev_root_tuple = _load_prev_active_root_tuple(repo_root_override=repo_root_override)

    new_iroot_ref = require_artifact_ref_v1(new_root_tuple.get("iroot"))
    prev_iroot_ref: dict[str, str] | None = None
    if prev_root_tuple is not None:
        prev_iroot_ref = require_artifact_ref_v1(prev_root_tuple.get("iroot"))

    # v1: recompute only when the index root changes (or if no previous root tuple).
    if prev_iroot_ref is not None and str(prev_iroot_ref.get("artifact_id", "")).strip() == str(new_iroot_ref.get("artifact_id", "")).strip():
        return

    evidence = summary.get("evidence")
    if not isinstance(evidence, dict):
        fail("SCHEMA_FAIL")
    ml_index_manifest_ref = require_artifact_ref_v1(evidence.get("ml_index_manifest_ref"))
    ml_index_manifest_path = verify_artifact_ref_v1(
        artifact_ref=ml_index_manifest_ref,
        base_dir=state_root,
        expected_relpath_prefix="eudrs_u/evidence/",
    )
    manifest_payload = gcj1_loads_and_verify_canonical(ml_index_manifest_path.read_bytes())
    if not isinstance(manifest_payload, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(manifest_payload)
    _validate_schema(manifest_payload, "ml_index_manifest_v1")
    manifest = require_ml_index_manifest_v1(manifest_payload)

    # The evidence manifest MUST correspond to the index root activated by the root tuple.
    if manifest.index_root_ref.get("artifact_id") != new_iroot_ref.get("artifact_id"):
        fail("NONDETERMINISTIC")

    # Load and validate codebook.
    codebook_path = verify_artifact_ref_v1(artifact_ref=manifest.codebook_ref, base_dir=staged_registry_tree_abs, expected_relpath_prefix="polymath/registry/eudrs_u/")
    codebook = decode_ml_index_codebook_v1(codebook_path.read_bytes())
    if int(codebook.K_u32) != int(manifest.codebook_size_u32) or int(codebook.d_u32) != int(manifest.key_dim_u32):
        fail("SCHEMA_FAIL")

    # Load and validate index root binary.
    index_root_path = verify_artifact_ref_v1(artifact_ref=manifest.index_root_ref, base_dir=staged_registry_tree_abs, expected_relpath_prefix="polymath/registry/eudrs_u/")
    index_root = decode_ml_index_root_v1(index_root_path.read_bytes())
    if int(index_root.K_u32) != int(manifest.codebook_size_u32):
        fail("SCHEMA_FAIL")
    if int(index_root.fanout_u32) != int(manifest.merkle_fanout_u32):
        fail("SCHEMA_FAIL")

    # Load + validate bucket listing (the only permitted bucket discovery mechanism).
    bucket_listing_path = verify_artifact_ref_v1(
        artifact_ref=manifest.bucket_listing_ref,
        base_dir=staged_registry_tree_abs,
        expected_relpath_prefix="polymath/registry/eudrs_u/",
    )
    bucket_listing_payload = gcj1_loads_and_verify_canonical(bucket_listing_path.read_bytes())
    if not isinstance(bucket_listing_payload, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(bucket_listing_payload)
    _validate_schema(bucket_listing_payload, "ml_index_bucket_listing_v1")
    bucket_listing = require_ml_index_bucket_listing_v1(bucket_listing_payload)

    # Deterministic on-disk page discovery + Merkle verification.
    pages_by_bucket, leaf_hashes_by_bucket = load_ml_index_pages_by_bucket_v1(base_dir=staged_registry_tree_abs, manifest=manifest)
    verify_ml_index_merkle_roots_v1(manifest=manifest, index_root=index_root, leaf_hashes_by_bucket=leaf_hashes_by_bucket)

    # Enforce MEM gates (recomputed deterministically from the index itself).
    def _load_page_bytes_by_ref(ref: dict[str, str]) -> bytes:
        path = verify_artifact_ref_v1(
            artifact_ref=ref,
            base_dir=staged_registry_tree_abs,
            expected_relpath_prefix="polymath/registry/eudrs_u/",
        )
        return path.read_bytes()

    verify_mem_gates_v1(
        index_manifest_obj=manifest_payload,
        codebook_bytes=codebook_path.read_bytes(),
        index_root_bytes=index_root_path.read_bytes(),
        bucket_listing_obj=bucket_listing_payload,
        load_page_bytes_by_ref=_load_page_bytes_by_ref,
    )


def verify(
    state_dir: Path,
    *,
    mode: str = "full",
    repo_root_override: Path | None = None,
) -> str:
    mode_s = str(mode).strip()
    if mode_s not in {"full", "replay"}:
        fail("MODE_UNSUPPORTED")

    state_root = _resolve_state_dir(state_dir)
    evidence_dir = state_root / EUDRS_U_EVIDENCE_DIR_REL
    if not evidence_dir.exists() or not evidence_dir.is_dir():
        fail("MISSING_STATE_INPUT")

    _summary_path, summary = _load_single_summary(evidence_dir)
    require_no_absolute_paths(summary)

    staged_registry_tree_rel = require_safe_relpath_v1(summary.get("staged_registry_tree_relpath"))
    if staged_registry_tree_rel != "eudrs_u/staged_registry_tree":
        fail("SCHEMA_FAIL")
    staged_registry_tree_abs = (state_root / staged_registry_tree_rel).resolve()
    try:
        staged_registry_tree_abs.relative_to(state_root.resolve())
    except Exception:
        fail("SCHEMA_FAIL")
    if not staged_registry_tree_abs.exists() or not staged_registry_tree_abs.is_dir():
        fail("MISSING_STATE_INPUT")

    # Verify evidence artifacts.
    evidence = summary.get("evidence")
    if not isinstance(evidence, dict):
        fail("SCHEMA_FAIL")

    evidence_keys = [
        "weights_manifest_ref",
        "ml_index_manifest_ref",
        "cac_ref",
        "ufc_ref",
        "cooldown_ledger_ref",
        "stability_metrics_ref",
        "determinism_cert_ref",
        "universality_cert_ref",
    ]
    for key in evidence_keys:
        ref = require_artifact_ref_v1(evidence.get(key))
        verify_artifact_ref_v1(artifact_ref=ref, base_dir=state_root, expected_relpath_prefix="eudrs_u/evidence/")

    # Verify proposed root tuple + staged activation pointer.
    proposed_root_tuple_ref = require_artifact_ref_v1(summary.get("proposed_root_tuple_ref"))
    if not str(proposed_root_tuple_ref.get("artifact_relpath", "")).endswith(".eudrs_u_root_tuple_v1.json"):
        fail("SCHEMA_FAIL")
    root_tuple_path = verify_artifact_ref_v1(
        artifact_ref=proposed_root_tuple_ref,
        base_dir=state_root,
        expected_relpath_prefix=f"{staged_registry_tree_rel}/polymath/registry/eudrs_u/roots/",
    )
    root_tuple = gcj1_loads_and_verify_canonical(root_tuple_path.read_bytes())
    if not isinstance(root_tuple, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(root_tuple)
    _verify_root_tuple_fields(dict(root_tuple))

    _verify_root_tuple_epoch(
        new_root_tuple=dict(root_tuple),
        repo_root_override=repo_root_override,
        enforce_increment=(mode_s == "full"),
    )

    _verify_sroot_system_manifest_binding(root_tuple=dict(root_tuple), staged_root=staged_registry_tree_abs)

    _verify_artifact_refs_in_root_tuple(root_tuple=dict(root_tuple), staged_root=staged_registry_tree_abs)

    # DMPL DRoot is required in this checkout; verify it authoritatively.
    if isinstance(root_tuple.get("droot"), dict):
        _verify_dmpl_droot_phase1(root_tuple=dict(root_tuple), staged_root=staged_registry_tree_abs)

        # Phase 3: DMPL opset compliance + (optional) plan replay verification.
        try:

            def _dmpl_aref(value: Any) -> dict[str, str]:
                try:
                    return require_artifact_ref_v1(value)
                except OmegaV18Error:
                    raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "bad ArtifactRef"})

            droot_ref = require_artifact_ref_v1(root_tuple.get("droot"))
            droot_path = verify_artifact_ref_v1(
                artifact_ref=droot_ref,
                base_dir=staged_registry_tree_abs,
                expected_relpath_prefix=_DMPL_REGISTRY_PREFIX,
            )
            droot_obj = gcj1_loads_and_verify_canonical(droot_path.read_bytes())
            if not isinstance(droot_obj, dict):
                fail("SCHEMA_FAIL")
            _validate_schema(droot_obj, "dmpl_droot_v1")

            config_id = str(droot_obj.get("dmpl_config_id", "")).strip()
            config_obj = _load_json_artifact_by_id_and_type(
                base_dir=staged_registry_tree_abs,
                expected_relpath_prefix=_DMPL_REGISTRY_PREFIX,
                artifact_id=config_id,
                artifact_type="dmpl_config_v1",
            )
            _validate_schema(config_obj, "dmpl_config_v1")

            modelpack_id = str(config_obj.get("active_modelpack_id", "")).strip()
            modelpack_obj = _load_json_artifact_by_id_and_type(
                base_dir=staged_registry_tree_abs,
                expected_relpath_prefix=_DMPL_REGISTRY_PREFIX,
                artifact_id=modelpack_id,
                artifact_type="dmpl_modelpack_v1",
            )
            _validate_schema(modelpack_obj, "dmpl_modelpack_v1")

            verify_dmpl_opset_v1(droot_obj=dict(droot_obj), config_obj=dict(config_obj), modelpack_obj=dict(modelpack_obj))

            enabled_b = config_obj.get("enabled_b")
            if not isinstance(enabled_b, bool):
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "enabled_b not bool"})

            dmpl_evidence_obj = summary.get("dmpl_evidence")

            resolver = _DMPLPromotionResolverV1(
                state_root=state_root,
                evidence_dir=evidence_dir,
                staged_registry_tree_abs=staged_registry_tree_abs,
            )

            if not bool(enabled_b):
                # Phase 4: disabled DMPL => summary must not claim DMPL evidence.
                if dmpl_evidence_obj is not None:
                    raise DMPLError(reason_code=DMPL_E_DISABLED, details={"hint": "dmpl_evidence present"})

            else:
                # Phase 4: enabled DMPL => dmpl_evidence is required and promotion-critical.
                if not isinstance(dmpl_evidence_obj, dict):
                    raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "missing dmpl_evidence"})
                if set(dmpl_evidence_obj.keys()) != {"schema_id", "plan_evidence", "train_evidence", "certificate_refs"}:
                    raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "dmpl_evidence keys"})
                if str(dmpl_evidence_obj.get("schema_id", "")).strip() != "dmpl_evidence_v1":
                    raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "dmpl_evidence schema_id"})

                plan_evidence = dmpl_evidence_obj.get("plan_evidence")
                if not isinstance(plan_evidence, list) or not plan_evidence:
                    raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "dmpl_evidence.plan_evidence empty"})

                train_evidence = dmpl_evidence_obj.get("train_evidence")
                if not isinstance(train_evidence, dict) or set(train_evidence.keys()) != {
                    "schema_id",
                    "dmpl_train_run_ref",
                    "dmpl_train_trace_ref",
                    "dmpl_train_receipt_ref",
                }:
                    raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "dmpl_evidence.train_evidence"})
                if str(train_evidence.get("schema_id", "")).strip() != "dmpl_train_evidence_v1":
                    raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "train_evidence schema_id"})

                cert_refs = dmpl_evidence_obj.get("certificate_refs")
                if not isinstance(cert_refs, dict):
                    raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "dmpl_evidence.certificate_refs"})
                expected_cert_keys = {"dmpl_cac_pack_ref", "dmpl_ufc_flow_ref", "dmpl_stab_report_ref", "dmpl_lasum_report_ref"}
                if set(cert_refs.keys()) != expected_cert_keys:
                    raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "certificate_refs keys"})
                for k in sorted(expected_cert_keys):
                    if not isinstance(cert_refs.get(k), dict):
                        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "missing certificate ref", "key": str(k)})

                # Verify training replay (promotion-critical).
                verify_dmpl_train_replay_v1(
                    root_tuple_obj=dict(root_tuple),
                    train_run_ref=_dmpl_aref(train_evidence.get("dmpl_train_run_ref")),
                    train_trace_ref=_dmpl_aref(train_evidence.get("dmpl_train_trace_ref")),
                    train_receipt_ref=_dmpl_aref(train_evidence.get("dmpl_train_receipt_ref")),
                    resolver=resolver,
                )

                # Enforce deterministic ordering by plan_query_ref.artifact_id asc.
                prev_pq_id: str | None = None
                for item in plan_evidence:
                    if not isinstance(item, dict):
                        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "plan_evidence item type"})
                    if str(item.get("schema_id", "")).strip() != "dmpl_plan_evidence_v1":
                        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "plan evidence schema_id"})
                    if set(item.keys()) != {"schema_id", "plan_query_ref", "rollout_trace_ref", "action_receipt_ref"}:
                        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "plan evidence keys"})
                    pq_ref = _dmpl_aref(item.get("plan_query_ref"))
                    rt_ref = _dmpl_aref(item.get("rollout_trace_ref"))
                    ar_ref = _dmpl_aref(item.get("action_receipt_ref"))

                    pq_id = str(pq_ref.get("artifact_id", "")).strip()
                    if prev_pq_id is not None and pq_id <= prev_pq_id:
                        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "plan_evidence not sorted"})
                    prev_pq_id = pq_id

                    try:
                        prefix = f"{staged_registry_tree_rel}/polymath/registry/eudrs_u/"
                        pq_bytes = resolver.load_artifact_ref_bytes(pq_ref, expected_relpath_prefix=prefix)
                        rt_bytes = resolver.load_artifact_ref_bytes(rt_ref, expected_relpath_prefix=prefix)
                        ar_bytes = resolver.load_artifact_ref_bytes(ar_ref, expected_relpath_prefix=prefix)
                        pq_obj = gcj1_loads_and_verify_canonical(pq_bytes)
                        rt_obj = gcj1_loads_and_verify_canonical(rt_bytes)
                        ar_obj = gcj1_loads_and_verify_canonical(ar_bytes)
                    except OmegaV18Error:
                        raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"hint": "dmpl evidence noncanonical"})
                    if not isinstance(pq_obj, dict) or not isinstance(rt_obj, dict) or not isinstance(ar_obj, dict):
                        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "dmpl evidence not dict"})

                    verify_dmpl_plan_replay_v1(
                        plan_query_obj=dict(pq_obj),
                        rollout_trace_obj=dict(rt_obj),
                        action_receipt_obj=dict(ar_obj),
                        resolver=resolver,
                    )

                # Certificates: promotion-critical in Phase 4.
                # Pass train evidence to the certificate verifier via resolver extension.
                resolver._dmpl_train_evidence_v1 = dict(train_evidence)
                verify_dmpl_certificates_gated_v1(
                    cert_refs_obj=dict(cert_refs),
                    plan_evidence_obj=[dict(it) for it in plan_evidence],
                    config_obj=dict(config_obj),
                    resolver=resolver,
                )

        except DMPLError as exc:
            fail(str(exc.reason_code))

    # The root tuple is staged under eudrs_u/staged_registry_tree/..., but the activation
    # pointer must reference the target repo relpath (without the staging prefix).
    expected_root_tuple_target_rel = proposed_root_tuple_ref["artifact_relpath"]
    staged_prefix = f"{staged_registry_tree_rel}/"
    if expected_root_tuple_target_rel.startswith(staged_prefix):
        expected_root_tuple_target_rel = expected_root_tuple_target_rel[len(staged_prefix) :]
    expected_root_tuple_target_ref = {
        "artifact_id": proposed_root_tuple_ref["artifact_id"],
        "artifact_relpath": expected_root_tuple_target_rel,
    }

    _verify_staged_active_pointer(
        staged_root=staged_registry_tree_abs,
        expected_root_tuple_ref=expected_root_tuple_target_ref,
    )

    _verify_ml_index_if_changed(
        summary=summary,
        new_root_tuple=root_tuple,
        state_root=state_root,
        staged_registry_tree_abs=staged_registry_tree_abs,
        repo_root_override=repo_root_override,
    )

    return "VALID"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="verify_eudrs_u_promotion_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args(argv)

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
