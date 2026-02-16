from __future__ import annotations

import json
from pathlib import Path

import pytest

from cdel.v17_0.runtime.sas_val_run_v1 import ValRunError, run_sas_val


def test_exec_requires_safe_receipt(tmp_path: Path) -> None:
    campaign = tmp_path / "campaign"
    src = Path("campaigns/rsi_sas_val_v17_0")
    import shutil

    shutil.copytree(src, campaign)

    # Force unsafe patch content (svc).
    patch_path = campaign / "patches" / "val_patch_manifest_v1.json"
    patch = json.loads(patch_path.read_text(encoding="utf-8"))
    patch["code_bytes_b64"] = "AQAA8A=="  # 0xF0000001 (svc)
    patch["declared_code_len_u32"] = 4
    payload = dict(patch)
    payload.pop("patch_id", None)
    import hashlib

    patch["patch_id"] = "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    patch_path.write_text(json.dumps(patch, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(ValRunError) as exc:
        run_sas_val(
            campaign_pack=campaign / "rsi_sas_val_pack_v17_0.json",
            out_dir=tmp_path / "out",
            campaign_tag="rsi_sas_val_v17_0",
        )
    assert str(exc.value) == "INVALID:EXEC_BEFORE_SAFE"

    state = tmp_path / "out" / "daemon" / "rsi_sas_val_v17_0" / "state"
    assert not (state / "candidate" / "exec" / "val_exec_backend_v1.json").exists()
