from __future__ import annotations

from pathlib import Path

import json
import pytest
from cdel.v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v10_0.verify_rsi_model_genesis_v1 import verify
from .utils import build_valid_state


def test_v10_0_heldout_leak(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path)
    shard_path = Path(state["corpus_shard_path"])
    lines = shard_path.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[0])
    obj["source"]["split"] = "HELDOUT"
    shard_path.write_text(json.dumps(obj) + "\n", encoding="utf-8")
    # Update manifest hash so we hit heldout leak check instead of shard mismatch
    manifest_dir = Path(state["state_dir"]) / "corpus" / "manifest"
    manifest_path = next(manifest_dir.glob("sha256_*.training_corpus_manifest_v1.json"))
    manifest = load_canon_json(manifest_path)
    manifest["shards"][0]["sha256"] = sha256_prefixed(shard_path.read_bytes())
    # rewrite manifest with new hash + filename
    new_hash = sha256_prefixed(canon_bytes(manifest))
    for path in manifest_dir.glob("sha256_*.training_corpus_manifest_v1.json"):
        path.unlink()
    new_path = manifest_dir / f"sha256_{new_hash.split(':',1)[1]}.training_corpus_manifest_v1.json"
    write_canon_json(new_path, manifest)
    with pytest.raises(CanonError, match="HELDOUT_LEAK"):
        verify(state["state_dir"], mode="prefix")
