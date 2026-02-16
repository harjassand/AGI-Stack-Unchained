"""Novelty scoring (v11.0)."""

from __future__ import annotations

from typing import Any

from .fixed_q32_v1 import q32_obj, q32_from_ratio


FEATURE_KEYS = [
    "param_count",
    "depth",
    "width",
    "attn_layers",
    "ssm_layers",
    "conv_layers",
    "rnn_layers",
    "memory_tokens",
]


def _feature_vector(fp: dict[str, Any]) -> list[int]:
    return [int(fp.get(k, 0)) for k in FEATURE_KEYS]


def compute_novelty(baseline_fp: dict[str, Any], candidate_fp: dict[str, Any]) -> dict[str, Any]:
    vb = _feature_vector(baseline_fp)
    vc = _feature_vector(candidate_fp)
    components: list[dict[str, Any]] = []
    sum_q = 0
    for b, c in zip(vb, vc):
        abs_diff = abs(int(c) - int(b))
        den = max(abs(int(b)), abs(int(c)), 1)
        comp = q32_from_ratio(abs_diff, den)
        components.append(comp)
        sum_q += int(comp["q"])
    novelty_q = sum_q // len(FEATURE_KEYS)
    report = {
        "schema_version": "sas_novelty_report_v1",
        "baseline_arch_id": baseline_fp.get("arch_id"),
        "candidate_arch_id": candidate_fp.get("arch_id"),
        "baseline_fingerprint_hash": baseline_fp.get("signature_hash"),
        "candidate_fingerprint_hash": candidate_fp.get("signature_hash"),
        "novelty_score_q32": q32_obj(novelty_q),
        "components_q32": components,
    }
    return report


def recompute_novelty_score(report: dict[str, Any], baseline_fp: dict[str, Any], candidate_fp: dict[str, Any]) -> int:
    # Return q32 integer
    vb = _feature_vector(baseline_fp)
    vc = _feature_vector(candidate_fp)
    sum_q = 0
    for b, c in zip(vb, vc):
        abs_diff = abs(int(c) - int(b))
        den = max(abs(int(b)), abs(int(c)), 1)
        comp = q32_from_ratio(abs_diff, den)
        sum_q += int(comp["q"])
    return sum_q // len(FEATURE_KEYS)


__all__ = ["compute_novelty", "recompute_novelty_score", "FEATURE_KEYS"]
