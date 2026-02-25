from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from tools.proposer_models import runtime_v1, store_v1


def _write_bundle(*, store_root: Path, adapter_sha: str) -> str:
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

    manifests_root = store_v1.ensure_model_store_layout(store_root)["manifests_root"]
    bundle_path = store_v1.manifest_path_for_id(
        manifests_root,
        digest=bundle_id,
        schema_name="proposer_model_bundle_v1",
    )
    write_canon_json(bundle_path, bundle)
    return bundle_id


def test_model_bundle_hash_integrity_v1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store_root = (tmp_path / "daemon" / "proposer_models" / "store").resolve()
    layout = store_v1.ensure_model_store_layout(store_root)

    declared_sha = "sha256:" + ("1" * 64)
    blob_name = store_v1.blob_filename(declared_sha, kind="adapter", ext="bin")
    blob_path = layout["blobs_root"] / blob_name
    blob_path.write_bytes(b"this payload does not match declared sha")

    bundle_id = _write_bundle(store_root=store_root, adapter_sha=declared_sha)
    monkeypatch.setattr(runtime_v1, "_default_store_root", lambda: store_root)

    with pytest.raises(runtime_v1.ProposerRuntimeError, match="BUNDLE_HASH_MISMATCH"):
        runtime_v1.generate_patch_deterministic(
            role="PATCH_DRAFTER_V1",
            prompt_text="draft a patch",
            model_bundle_id=bundle_id,
            seed_u64=7,
            max_new_tokens_u32=32,
        )
