from __future__ import annotations

import sys
from pathlib import Path

_CDEL_ROOT = Path(__file__).resolve().parents[3]
if str(_CDEL_ROOT) not in sys.path:
    sys.path.insert(0, str(_CDEL_ROOT))

from cdel.v19_0.tests_world_federation.helpers import (
    budget,
    make_binding,
    make_entry,
    make_manifest,
    make_sip_profile,
    make_world_snapshot,
)
from cdel.v19_0.world.check_world_snapshot_v1 import check_world_snapshot
from cdel.v19_0.world.merkle_v1 import compute_world_root
from cdel.v19_0.world.sip_v1 import run_sip


def test_world_live_dependency_missing_snapshot_dependency_safe_halt() -> None:
    entry = make_entry("inputs/a.txt", b"sealed-world")
    manifest = make_manifest([entry])
    sip_profile = make_sip_profile()

    snapshot_id = "sha256:" + ("3" * 64)
    missing_dependency = "sha256:" + ("f" * 64)
    binding = make_binding(
        task_id="eval_live_call",
        world_snapshot_id=snapshot_id,
        manifest_id=manifest["manifest_id"],
        deps=[entry["content_id"], missing_dependency],
        eval_inputs=[entry["content_id"], missing_dependency],
    )

    receipt = run_sip(
        manifest=manifest,
        artifact_bytes_by_content_id={entry["content_id"]: b"sealed-world"},
        sip_profile=sip_profile,
        world_task_bindings=[binding],
        world_snapshot_id=snapshot_id,
        budget_spec=budget(),
    )

    assert receipt["outcome"] == "SAFE_HALT"
    assert receipt["reason_code"] == "NON_INTERFERENCE_FAIL"


def test_world_root_mismatch_after_manifest_change_safe_halt() -> None:
    original_entry = make_entry("inputs/blob.bin", b"alpha")
    original_manifest = make_manifest([original_entry])
    original_root = compute_world_root(original_manifest)

    sip_profile = make_sip_profile()
    snapshot_id = "sha256:" + ("4" * 64)
    binding = make_binding(
        task_id="eval_static",
        world_snapshot_id=snapshot_id,
        manifest_id=original_manifest["manifest_id"],
        deps=[original_entry["content_id"]],
        eval_inputs=[original_entry["content_id"]],
    )

    ingestion_receipt = run_sip(
        manifest=original_manifest,
        artifact_bytes_by_content_id={original_entry["content_id"]: b"alpha"},
        sip_profile=sip_profile,
        world_task_bindings=[binding],
        world_snapshot_id=snapshot_id,
        budget_spec=budget(),
    )
    assert ingestion_receipt["outcome"] == "ACCEPT"

    tampered_entry = make_entry("inputs/blob.bin", b"beta")
    tampered_manifest = make_manifest([tampered_entry])
    tampered_root = compute_world_root(tampered_manifest)
    assert tampered_root != original_root

    snapshot = make_world_snapshot(
        manifest=tampered_manifest,
        ingestion_receipt=ingestion_receipt,
        world_root=original_root,
    )

    receipt = check_world_snapshot(
        snapshot=snapshot,
        manifest=tampered_manifest,
        ingestion_receipt=ingestion_receipt,
        world_task_bindings=None,
        budget_spec=budget(),
    )

    assert receipt["outcome"] == "SAFE_HALT"
    assert receipt["reason_code"] == "WORLD_ROOT_MISMATCH"
