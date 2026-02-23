from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0.ccap_runtime_v1 import (
    apply_patch_bytes,
    build_replace_file_patch_bytes,
    classify_patch_apply_exception,
    patch_touched_relpaths,
)


def test_replace_file_patch_applies_with_base_hash_guard(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "campaigns" / "sample.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    before = b'{"enabled":true,"value":1}\n'
    after = b'{"enabled":true,"value":2}\n'
    target.write_bytes(before)

    patch_bytes = build_replace_file_patch_bytes(
        target_relpath="campaigns/sample.json",
        expected_base_bytes=before,
        new_bytes=after,
    )

    assert patch_touched_relpaths(patch_bytes=patch_bytes) == ["campaigns/sample.json"]
    apply_patch_bytes(workspace_root=workspace, patch_bytes=patch_bytes)
    assert target.read_bytes() == after


def test_replace_file_patch_refutes_on_base_mismatch(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "campaigns" / "sample.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    before = b'{"enabled":true,"value":1}\n'
    target.write_bytes(before)

    patch_bytes = build_replace_file_patch_bytes(
        target_relpath="campaigns/sample.json",
        expected_base_bytes=before,
        new_bytes=b'{"enabled":true,"value":2}\n',
    )
    target.write_bytes(b'{"enabled":true,"value":3}\n')

    with pytest.raises(RuntimeError, match="patch_base_mismatch"):
        apply_patch_bytes(workspace_root=workspace, patch_bytes=patch_bytes)

    classified = classify_patch_apply_exception(exc=RuntimeError("patch_base_mismatch: sample"))
    assert classified["refutation_code"] == "PATCH_BASE_MISMATCH"
    assert classified["patch_apply_fail_code"] == "JSON_CANON_MISMATCH"
