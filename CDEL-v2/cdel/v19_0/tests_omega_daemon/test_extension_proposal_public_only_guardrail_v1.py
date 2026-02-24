from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0.omega_common_v1 import OmegaV18Error
from cdel.v19_0.verify_kernel_extension_proposal_v1 import verify_extension_proposal_dir
from cdel.v1_7r.canon import write_canon_json


def _hash(value: dict[str, object]) -> str:
    from cdel.v18_0.omega_common_v1 import canon_hash_obj

    return canon_hash_obj(value)


def _with_declared_id(payload: dict[str, object], id_field: str) -> dict[str, object]:
    out = dict(payload)
    out.pop(id_field, None)
    out[id_field] = _hash(out)
    return out


def _write_hashed(promotion_dir: Path, name: str, payload: dict[str, object], id_field: str) -> None:
    promotion_dir.mkdir(parents=True, exist_ok=True)
    write_canon_json(promotion_dir / name, payload)
    digest = _hash(payload)
    hex_digest = digest.split(":", 1)[1]
    write_canon_json(promotion_dir / f"sha256_{hex_digest}.{name}", payload)


def test_extension_proposal_public_only_guardrail_v1(tmp_path: Path) -> None:
    anchor_ek_id = "sha256:" + ("2" * 64)
    suite_manifest = _with_declared_id(
        {
            "schema_version": "benchmark_suite_manifest_v1",
            "suite_name": "private_hidden_suite",
            "suite_runner_relpath": "tools/omega/omega_benchmark_suite_composite_v1.py",
            "visibility": "HIDDEN",
            "labels": ["internal"],
            "metrics": {"q32_metric_ids": ["accuracy_q32"], "public_only_b": False},
        },
        "suite_id",
    )
    suite_id = str(suite_manifest["suite_id"])
    suite_set = _with_declared_id(
        {
            "schema_version": "benchmark_suite_set_v1",
            "suite_set_kind": "EXTENSION",
            "anchor_ek_id": anchor_ek_id,
            "suites": [
                {
                    "suite_id": suite_id,
                    "suite_manifest_id": suite_id,
                    "suite_manifest_relpath": "benchmark_suite_manifest_v1.json",
                    "ordinal_u64": 0,
                }
            ],
        },
        "suite_set_id",
    )
    ext_spec = _with_declared_id(
        {
            "schema_version": "kernel_extension_spec_v1",
            "anchor_ek_id": anchor_ek_id,
            "extension_name": "apa_hidden_ext",
            "suite_set_id": str(suite_set["suite_set_id"]),
            "suite_set_relpath": "benchmark_suite_set_v1.json",
            "additive_only_b": True,
        },
        "extension_spec_id",
    )

    promotion_dir = (tmp_path / "promotion").resolve()
    _write_hashed(promotion_dir, "kernel_extension_spec_v1.json", ext_spec, "extension_spec_id")
    _write_hashed(promotion_dir, "benchmark_suite_manifest_v1.json", suite_manifest, "suite_id")
    _write_hashed(promotion_dir, "benchmark_suite_set_v1.json", suite_set, "suite_set_id")

    with pytest.raises(OmegaV18Error) as exc:
        verify_extension_proposal_dir(promotion_dir=promotion_dir)
    assert "PHASE1_PUBLIC_ONLY_VIOLATION" in str(exc.value)
