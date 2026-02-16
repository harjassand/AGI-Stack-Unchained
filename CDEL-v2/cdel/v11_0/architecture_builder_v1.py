"""Architecture builder helpers (v11.0)."""

from __future__ import annotations

from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed

ALLOWED_FAMILIES = {
    "toy_transformer_v1",
    "toy_transformer_memory_v1",
    "toy_ssm_v1",
    "toy_convseq_v1",
    "toy_hybrid_attn_ssm_v1",
    "toy_rnn_memory_v1",
}


class ArchBuildError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise ArchBuildError(reason)


def _require_int(obj: dict[str, Any], key: str) -> int:
    val = obj.get(key)
    if not isinstance(val, int):
        _fail("SCHEMA_INVALID")
    return val


def compute_arch_id(arch_ir: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(arch_ir))


def _extract_hparams(hparams: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key in [
        "depth",
        "width",
        "attn_layers",
        "ssm_layers",
        "conv_layers",
        "rnn_layers",
        "memory_tokens",
    ]:
        val = hparams.get(key, 0)
        if not isinstance(val, int):
            _fail("SCHEMA_INVALID")
        out[key] = int(val)
    if out["depth"] < 1 or out["width"] < 1:
        _fail("SCHEMA_INVALID")
    return out


def _compute_param_count(hparams: dict[str, int]) -> int:
    depth = hparams["depth"]
    width = hparams["width"]
    attn_layers = hparams["attn_layers"]
    ssm_layers = hparams["ssm_layers"]
    conv_layers = hparams["conv_layers"]
    rnn_layers = hparams["rnn_layers"]
    memory_tokens = hparams["memory_tokens"]
    # Deterministic toy formula.
    base = width * width
    extra = (attn_layers + ssm_layers + conv_layers + rnn_layers) * width * 4
    mem = memory_tokens * max(1, width)
    params = depth * base + extra + mem
    return max(1, int(params))


def _compute_activation_mb(hparams: dict[str, int]) -> int:
    depth = hparams["depth"]
    width = hparams["width"]
    activation = (depth * width) // 32
    return max(1, int(activation))


def enforce_allowlist(arch_ir: dict[str, Any], allowlist: dict[str, Any]) -> None:
    family = arch_ir.get("arch_family")
    if family not in ALLOWED_FAMILIES:
        _fail("ALLOWLIST_VIOLATION")
    allowed_families = allowlist.get("allowed_families") or []
    if family not in allowed_families:
        _fail("ALLOWLIST_VIOLATION")
    hparams = _extract_hparams(arch_ir.get("hyperparams") or {})
    family_constraints = (allowlist.get("family_constraints") or {}).get(family) or {}
    max_depth = family_constraints.get("max_depth")
    max_width = family_constraints.get("max_width")
    max_params = family_constraints.get("max_params")
    if isinstance(max_depth, int) and hparams["depth"] > max_depth:
        _fail("ALLOWLIST_VIOLATION")
    if isinstance(max_width, int) and hparams["width"] > max_width:
        _fail("ALLOWLIST_VIOLATION")
    if isinstance(max_params, int) and _compute_param_count(hparams) > max_params:
        _fail("ALLOWLIST_VIOLATION")


def build_manifest(
    *,
    arch_ir: dict[str, Any],
    builder_version: str,
    toolchain_hash: str,
) -> dict[str, Any]:
    if not isinstance(arch_ir, dict) or arch_ir.get("schema_version") != "sas_arch_ir_v1":
        _fail("SCHEMA_INVALID")
    family = arch_ir.get("arch_family")
    if family not in ALLOWED_FAMILIES:
        _fail("ALLOWLIST_VIOLATION")
    arch_seed = arch_ir.get("arch_seed")
    if not isinstance(arch_seed, int):
        _fail("SCHEMA_INVALID")
    model_io = arch_ir.get("model_io")
    if not isinstance(model_io, dict):
        _fail("SCHEMA_INVALID")
    _require_int(model_io, "vocab_size")
    _require_int(model_io, "seq_len")
    if model_io.get("task_head") != "lm_head_v1":
        _fail("SCHEMA_INVALID")
    hparams = _extract_hparams(arch_ir.get("hyperparams") or {})
    constraints = arch_ir.get("constraints")
    if not isinstance(constraints, dict):
        _fail("SCHEMA_INVALID")
    _require_int(constraints, "max_params")
    _require_int(constraints, "max_activation_mb")

    arch_id = compute_arch_id(arch_ir)
    param_count = _compute_param_count(hparams)
    activation_mb = _compute_activation_mb(hparams)
    if param_count > int(constraints["max_params"]):
        _fail("PARAM_BUDGET_EXCEEDED")
    if activation_mb > int(constraints["max_activation_mb"]):
        _fail("PARAM_BUDGET_EXCEEDED")

    graph_payload = {
        "arch_id": arch_id,
        "arch_family": family,
        "model_io": model_io,
        "hyperparams": hparams,
        "constraints": constraints,
        "param_count": param_count,
        "activation_mb": activation_mb,
        "builder_version": builder_version,
    }
    arch_graph_hash = sha256_prefixed(canon_bytes(graph_payload))

    init_payload = {
        "arch_id": arch_id,
        "arch_seed": arch_seed,
        "arch_graph_hash": arch_graph_hash,
        "builder_version": builder_version,
        "toolchain_hash": toolchain_hash,
    }
    init_weights_hash = sha256_prefixed(canon_bytes(init_payload))

    manifest = {
        "schema_version": "sas_arch_manifest_v1",
        "arch_id": arch_id,
        "arch_family": family,
        "arch_seed": arch_seed,
        "model_io": model_io,
        "hyperparams": hparams,
        "constraints": constraints,
        "param_count": param_count,
        "activation_mb": activation_mb,
        "arch_graph_hash": arch_graph_hash,
        "init_weights_hash": init_weights_hash,
        "builder_version": builder_version,
    }
    return manifest


__all__ = ["compute_arch_id", "build_manifest", "enforce_allowlist", "ArchBuildError"]
