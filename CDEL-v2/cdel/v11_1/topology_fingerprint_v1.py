"""Topology fingerprint computation (v11.0)."""

from __future__ import annotations

from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed


def compute_fingerprint(manifest: dict[str, Any]) -> dict[str, Any]:
    hparams = manifest.get("hyperparams") or {}
    fingerprint = {
        "schema_version": "sas_topology_fingerprint_v1",
        "arch_id": manifest.get("arch_id"),
        "arch_family": manifest.get("arch_family"),
        "arch_graph_hash": manifest.get("arch_graph_hash"),
        "param_count": int(manifest.get("param_count", 0)),
        "depth": int(hparams.get("depth", 0)),
        "width": int(hparams.get("width", 0)),
        "attn_layers": int(hparams.get("attn_layers", 0)),
        "ssm_layers": int(hparams.get("ssm_layers", 0)),
        "conv_layers": int(hparams.get("conv_layers", 0)),
        "rnn_layers": int(hparams.get("rnn_layers", 0)),
        "memory_tokens": int(hparams.get("memory_tokens", 0)),
        "signature_hash": "",
    }
    payload = dict(fingerprint)
    payload.pop("signature_hash", None)
    fingerprint["signature_hash"] = sha256_prefixed(canon_bytes(payload))
    return fingerprint


__all__ = ["compute_fingerprint"]
