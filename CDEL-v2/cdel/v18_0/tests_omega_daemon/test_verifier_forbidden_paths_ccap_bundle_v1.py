from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0.omega_allowlists_v1 import load_allowlists
from cdel.v18_0.verify_rsi_omega_daemon_v1 import _verify_forbidden_paths
from cdel.v18_0.omega_common_v1 import OmegaV18Error, canon_hash_obj
from cdel.v1_7r.canon import write_canon_json


def _allowlists() -> dict:
    path = Path(__file__).resolve().parents[4] / "campaigns" / "rsi_omega_daemon_v18_0" / "omega_allowlists_v1.json"
    return load_allowlists(path)[0]


def test_ccap_bundle_paths_are_validated_without_global_allowlist(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    subrun = state_root / "subruns" / "x"
    subrun.mkdir(parents=True, exist_ok=True)

    bundle = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": "sha256:" + ("1" * 64),
        "ccap_relpath": "ccap/sha256_" + ("1" * 64) + ".ccap_v1.json",
        "patch_relpath": "ccap/blobs/sha256_" + ("2" * 64) + ".patch",
        "touched_paths": [
            "ccap/sha256_" + ("1" * 64) + ".ccap_v1.json",
            "ccap/blobs/sha256_" + ("2" * 64) + ".patch",
        ],
        "activation_key": "k",
    }
    bundle_hash = canon_hash_obj(bundle)
    write_canon_json(subrun / f"sha256_{bundle_hash.split(':', 1)[1]}.omega_promotion_bundle_ccap_v1.json", bundle)

    receipt = {"promotion_bundle_hash": bundle_hash}
    _verify_forbidden_paths(state_root=state_root, promotion_receipt=receipt, allowlists=_allowlists())


def test_ccap_bundle_rejects_omega_cache_touched_path(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    subrun = state_root / "subruns" / "x"
    subrun.mkdir(parents=True, exist_ok=True)

    bundle = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": "sha256:" + ("1" * 64),
        "ccap_relpath": "ccap/sha256_" + ("1" * 64) + ".ccap_v1.json",
        "patch_relpath": "ccap/blobs/sha256_" + ("2" * 64) + ".patch",
        "touched_paths": [
            "ccap/sha256_" + ("1" * 64) + ".ccap_v1.json",
            "ccap/blobs/sha256_" + ("2" * 64) + ".patch",
            "foo/.omega_cache/bar",
        ],
        "activation_key": "k",
    }
    bundle_hash = canon_hash_obj(bundle)
    write_canon_json(subrun / f"sha256_{bundle_hash.split(':', 1)[1]}.omega_promotion_bundle_ccap_v1.json", bundle)

    receipt = {"promotion_bundle_hash": bundle_hash}
    with pytest.raises(OmegaV18Error):
        _verify_forbidden_paths(state_root=state_root, promotion_receipt=receipt, allowlists=_allowlists())
