from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from tools.proposer_models import runtime_v1, store_v1


def _write_valid_bundle(*, store_root: Path) -> str:
    payload = b"adapter-bytes"
    adapter_sha = store_v1.sha256_bytes(payload)

    layout = store_v1.ensure_model_store_layout(store_root)
    blob_path = layout["blobs_root"] / store_v1.blob_filename(adapter_sha, kind="adapter", ext="bin")
    blob_path.write_bytes(payload)

    bundle_no_id = {
        "schema_version": "proposer_model_bundle_v1",
        "role": "PATCH_DRAFTER_V1",
        "base_model_ref": "unit-test-base",
        "tokenizer_ref": "unit-test-tokenizer",
        "method": "SFT_LORA",
        "dataset_manifest_id": "sha256:" + ("2" * 64),
        "train_config_id": "sha256:" + ("3" * 64),
        "adapter_files": [{"relpath": "adapter.bin", "sha256": adapter_sha}],
        "quantization": {"kind": "NONE", "bnb_compute_dtype": "bf16"},
        "train_metrics": {"final_loss_q32": 0, "steps_u64": 1},
    }
    bundle_id = str(canon_hash_obj(bundle_no_id))
    bundle = dict(bundle_no_id)
    bundle["bundle_id"] = bundle_id
    bundle_path = store_v1.manifest_path_for_id(
        layout["manifests_root"],
        digest=bundle_id,
        schema_name="proposer_model_bundle_v1",
    )
    write_canon_json(bundle_path, bundle)
    return bundle_id


def test_runtime_load_fail_closed_v1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store_root = (tmp_path / "daemon" / "proposer_models" / "store").resolve()
    bundle_id = _write_valid_bundle(store_root=store_root)

    monkeypatch.setattr(runtime_v1, "_default_store_root", lambda: store_root)

    def _deps_missing() -> tuple[object, object, object, object, object]:
        raise runtime_v1.ProposerRuntimeError("MODEL_RUNTIME_DEPS_MISSING")

    monkeypatch.setattr(runtime_v1, "_import_runtime_deps", _deps_missing)

    with pytest.raises(runtime_v1.ProposerRuntimeError) as exc:
        runtime_v1.generate_patch_deterministic(
            role="PATCH_DRAFTER_V1",
            prompt_text="emit unified diff",
            model_bundle_id=bundle_id,
            seed_u64=13,
            max_new_tokens_u32=64,
        )

    assert str(exc.value) == "MODEL_RUNTIME_DEPS_MISSING"
    assert "Traceback" not in str(exc.value)
