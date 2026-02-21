"""Deterministic retention/sampling/summary-planning helpers (R7 baseline)."""

from __future__ import annotations

from typing import Any

from ..common_v1 import canon_hash_obj, ensure_sha256, validate_schema, verify_object_id

_Q32_ONE = 1 << 32


def _content_rows_from_manifest(world_manifest: dict[str, Any]) -> list[tuple[str, str]]:
    validate_schema(world_manifest, "world_snapshot_manifest_v1")
    rows = world_manifest.get("entries")
    if not isinstance(rows, list):
        raise RuntimeError("SCHEMA_FAIL")
    out: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL")
        logical_path = str(row.get("logical_path", "")).strip()
        if not logical_path:
            raise RuntimeError("SCHEMA_FAIL")
        content_id = ensure_sha256(row.get("content_id"), reason="SCHEMA_FAIL")
        out.append((logical_path, content_id))
    out.sort(key=lambda item: (item[0], item[1]))
    return out


def _stable_pick(content_ids: list[str], *, sampling_rate_q32: int, seed_u64: int) -> list[str]:
    if not content_ids:
        return []
    rate = max(0, min(_Q32_ONE, int(sampling_rate_q32)))
    k = int((len(content_ids) * rate) // _Q32_ONE)
    if rate > 0 and k == 0:
        k = 1
    keyed = sorted(
        content_ids,
        key=lambda cid: canon_hash_obj(
            {
                "schema_version": "epistemic_sampling_key_v1",
                "seed_u64": int(seed_u64),
                "content_id": cid,
            }
        ),
    )
    return keyed[:k]


def build_retention_artifacts(
    *,
    retention_policy: dict[str, Any],
    capsule: dict[str, Any],
    world_manifest: dict[str, Any],
    sampling_seed_u64: int,
) -> dict[str, dict[str, Any]]:
    validate_schema(retention_policy, "epistemic_retention_policy_v1")
    validate_schema(capsule, "epistemic_capsule_v1")

    policy_id = verify_object_id(retention_policy, id_field="policy_id")
    capsule_id = ensure_sha256(capsule.get("capsule_id"), reason="SCHEMA_FAIL")
    content_rows = _content_rows_from_manifest(world_manifest)
    content_ids = sorted({cid for _logical_path, cid in content_rows})

    sampling_rate_q32 = int(retention_policy.get("sampling_rate_q32", 0))
    sampled_ids = _stable_pick(
        content_ids,
        sampling_rate_q32=sampling_rate_q32,
        seed_u64=int(sampling_seed_u64),
    )

    candidate_raw: list[str] = []
    candidate_mob: list[str] = []
    for logical_path, content_id in content_rows:
        path = logical_path.lower()
        if "/raw/" in path or "/chunks/" in path:
            candidate_raw.append(content_id)
        if "/mob/" in path or "/mobs/" in path:
            candidate_mob.append(content_id)
    candidate_raw = sorted(set(candidate_raw))
    candidate_mob = sorted(set(candidate_mob))

    deletion_plan = {
        "schema_version": "epistemic_deletion_plan_v1",
        "plan_id": "sha256:" + ("0" * 64),
        "policy_id": policy_id,
        "capsule_id": capsule_id,
        "candidate_raw_blob_ids": sorted(candidate_raw),
        "candidate_mob_blob_ids": sorted(candidate_mob),
        "planned_delete_count_u64": int(len(candidate_raw) + len(candidate_mob)),
        "dry_run_b": str(retention_policy.get("deletion_mode", "PLAN_ONLY")) != "EXECUTE",
        "reason_code": "RETENTION_PLAN_READY",
    }
    deletion_plan["plan_id"] = canon_hash_obj({k: v for k, v in deletion_plan.items() if k != "plan_id"})
    validate_schema(deletion_plan, "epistemic_deletion_plan_v1")
    verify_object_id(deletion_plan, id_field="plan_id")

    sampling_manifest = {
        "schema_version": "epistemic_sampling_manifest_v1",
        "manifest_id": "sha256:" + ("0" * 64),
        "policy_id": policy_id,
        "capsule_id": capsule_id,
        "source_content_count_u64": int(len(content_ids)),
        "sampled_content_ids": list(sampled_ids),
        "sample_count_u64": int(len(sampled_ids)),
        "sampling_seed_u64": int(max(0, int(sampling_seed_u64))),
        "sampling_rate_q32": int(sampling_rate_q32),
    }
    sampling_manifest["manifest_id"] = canon_hash_obj(
        {k: v for k, v in sampling_manifest.items() if k != "manifest_id"}
    )
    validate_schema(sampling_manifest, "epistemic_sampling_manifest_v1")
    verify_object_id(sampling_manifest, id_field="manifest_id")

    source_root = canon_hash_obj(
        {
            "schema_version": "epistemic_source_content_root_v1",
            "content_ids": list(content_ids),
        }
    )
    summary_content_id = canon_hash_obj(
        {
            "schema_version": "epistemic_summary_content_stub_v1",
            "capsule_id": capsule_id,
            "sample_manifest_id": sampling_manifest["manifest_id"],
        }
    )
    summary_proof = {
        "schema_version": "epistemic_summary_proof_v1",
        "proof_id": "sha256:" + ("0" * 64),
        "capsule_id": capsule_id,
        "source_content_ids_root": source_root,
        "summary_content_id": summary_content_id,
        "transform_contract_id": canon_hash_obj(
            {
                "schema_version": "epistemic_summary_transform_contract_v1",
                "policy_id": policy_id,
                "required_b": bool(retention_policy.get("summary_proof_required_b", False)),
            }
        ),
        "verifier_commitment_hash": canon_hash_obj(
            {
                "schema_version": "epistemic_summary_verifier_binding_v1",
                "deletion_plan_id": deletion_plan["plan_id"],
                "sampling_manifest_id": sampling_manifest["manifest_id"],
            }
        ),
        "outcome": "OK",
    }
    summary_proof["proof_id"] = canon_hash_obj({k: v for k, v in summary_proof.items() if k != "proof_id"})
    validate_schema(summary_proof, "epistemic_summary_proof_v1")
    verify_object_id(summary_proof, id_field="proof_id")

    return {
        "deletion_plan": deletion_plan,
        "sampling_manifest": sampling_manifest,
        "summary_proof": summary_proof,
    }


__all__ = ["build_retention_artifacts"]
