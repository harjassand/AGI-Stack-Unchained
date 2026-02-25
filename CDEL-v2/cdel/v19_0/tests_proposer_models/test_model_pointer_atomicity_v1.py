from __future__ import annotations

import json
from pathlib import Path

from tools.proposer_models import pointers_v1


def test_model_pointer_atomicity_v1(tmp_path: Path) -> None:
    active_root = (tmp_path / "daemon" / "proposer_models" / "active").resolve()
    bundle_a = "sha256:" + ("a" * 64)
    bundle_b = "sha256:" + ("b" * 64)

    for idx in range(20):
        expected = bundle_a if (idx % 2 == 0) else bundle_b
        path = pointers_v1.write_active_pointer_atomic(
            active_root=active_root,
            role="PATCH_DRAFTER_V1",
            active_bundle_id=expected,
            updated_tick_u64=idx,
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["active_bundle_id"] == expected
        assert int(payload["updated_tick_u64"]) == idx

        loaded = pointers_v1.load_active_pointer(active_root=active_root, role="PATCH_DRAFTER_V1")
        assert loaded is not None
        assert str(loaded.get("active_bundle_id")) == expected
