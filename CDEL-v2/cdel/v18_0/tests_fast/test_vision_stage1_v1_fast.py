from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_loads_and_verify_canonical, sha256_prefixed
from cdel.v18_0.eudrs_u.qxwmr_canon_wl_v1 import canon_state_packed_v1
from cdel.v18_0.eudrs_u.verify_vision_stage1_v1 import verify
from cdel.v18_0.omega_common_v1 import OmegaV18Error, validate_schema


_RUN_IDS = [
    # Printed by tools/vision/generate_vision_stage1_goldens_v1.py
    "sha256:aa4d750da3b7bf4be4fc329c6c226220b7f2e8638c8bf0ec04232519c032ed35",  # golden_move_v1
    "sha256:414abcec0ec00a4160eeb585b6f331e2bc2f17677c23c3b167537e8a3a1afacc",  # golden_split_v1
    "sha256:c046feaf1c1272fff1e28d5091038e44c76b04a7c2369748f40ac4cd5f0e37a3",  # golden_merge_occlude_v1
]


def _find_superproject_root() -> Path | None:
    here = Path(__file__).resolve()
    for anc in [here, *here.parents]:
        if (anc / "polymath/registry/eudrs_u/vision").is_dir():
            return anc
    return None


def _golden_manifest_paths(root: Path) -> list[Path]:
    runs_dir = root / "polymath/registry/eudrs_u/vision/perception/runs"
    out: list[Path] = []
    for rid in _RUN_IDS:
        assert rid.startswith("sha256:")
        out.append(runs_dir / f"sha256_{rid.split(':', 1)[1]}.vision_perception_run_manifest_v1.json")
    return out


_SUPERPROJECT_ROOT = _find_superproject_root()
if _SUPERPROJECT_ROOT is None:
    pytest.skip("requires polymath vision registry fixtures (run via AGI-Stack)", allow_module_level=True)
if not all(path.exists() for path in _golden_manifest_paths(_SUPERPROJECT_ROOT)):
    pytest.skip("requires generated stage1 vision goldens", allow_module_level=True)


def _repo_root() -> Path:
    assert _SUPERPROJECT_ROOT is not None
    return _SUPERPROJECT_ROOT


def _hex64(sha256_id: str) -> str:
    assert sha256_id.startswith("sha256:")
    return sha256_id.split(":", 1)[1]


def _hash_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def test_stage1_goldens_exist_and_hash_match_filenames() -> None:
    repo = _repo_root()
    runs_dir = repo / "polymath/registry/eudrs_u/vision/perception/runs"

    for rid in _RUN_IDS:
        p = runs_dir / f"sha256_{_hex64(rid)}.vision_perception_run_manifest_v1.json"
        assert p.exists()
        assert _hash_file(p) == rid


def test_stage1_goldens_verify_and_artifact_hashes_match(tmp_path: Path) -> None:
    repo = _repo_root()

    # Copy only the vision subtree into a staged_registry_tree (no symlinks: verifier resolves paths).
    state_dir = tmp_path
    staged = state_dir / "eudrs_u" / "staged_registry_tree"
    src_vision = repo / "polymath/registry/eudrs_u/vision"
    dst_vision = staged / "polymath/registry/eudrs_u/vision"
    if dst_vision.exists():
        shutil.rmtree(dst_vision)
    dst_vision.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_vision, dst_vision)

    for rid in _RUN_IDS:
        run_path = staged / f"polymath/registry/eudrs_u/vision/perception/runs/sha256_{_hex64(rid)}.vision_perception_run_manifest_v1.json"
        assert run_path.exists()

        # Verifier recomputes masks, reports, tracks, events, and QXWMR canonical states.
        receipt = verify(state_dir, run_manifest_path=run_path)
        assert receipt == {"schema_id": "vision_stage1_verify_receipt_v1", "verdict": "VALID"}

        # Additionally assert content hashes match embedded refs (mask/report/track/event/state).
        run_obj = gcj1_loads_and_verify_canonical(run_path.read_bytes())
        assert isinstance(run_obj, dict)
        validate_schema(run_obj, "vision_perception_run_manifest_v1")

        # Frame reports + qxwmr state artifacts
        for row in list(run_obj.get("frame_reports", [])):
            idx = int(row["frame_index_u32"])
            rep_ref = row["report_ref"]
            rep_path = staged / rep_ref["artifact_relpath"]
            assert rep_path.exists()
            assert _hash_file(rep_path) == rep_ref["artifact_id"]
            rep_obj = gcj1_loads_and_verify_canonical(rep_path.read_bytes())
            assert isinstance(rep_obj, dict)
            validate_schema(rep_obj, "vision_perception_frame_report_v1")
            assert int(rep_obj["frame_index_u32"]) == idx

            for obj in list(rep_obj.get("objects", [])):
                mask_ref = obj["mask_ref"]
                mask_path = staged / mask_ref["artifact_relpath"]
                assert mask_path.exists()
                assert _hash_file(mask_path) == mask_ref["artifact_id"]

        for row in list(run_obj.get("qxwmr_states", [])):
            state_ref = row["state_ref"]
            state_path = staged / state_ref["artifact_relpath"]
            assert state_path.exists()
            raw = state_path.read_bytes()
            assert sha256_prefixed(raw) == state_ref["artifact_id"]
            # Canon is idempotent.
            assert canon_state_packed_v1(raw) == raw

        # Track / event manifests
        track_ref = run_obj["track_manifest_ref"]
        track_path = staged / track_ref["artifact_relpath"]
        assert track_path.exists()
        assert _hash_file(track_path) == track_ref["artifact_id"]
        track_obj = gcj1_loads_and_verify_canonical(track_path.read_bytes())
        assert isinstance(track_obj, dict)
        validate_schema(track_obj, "vision_track_manifest_v1")

        event_ref = run_obj["event_manifest_ref"]
        event_path = staged / event_ref["artifact_relpath"]
        assert event_path.exists()
        assert _hash_file(event_path) == event_ref["artifact_id"]
        event_obj = gcj1_loads_and_verify_canonical(event_path.read_bytes())
        assert isinstance(event_obj, dict)
        validate_schema(event_obj, "vision_event_manifest_v1")


def test_stage1_verifier_fails_closed_on_missing_artifact(tmp_path: Path) -> None:
    repo = _repo_root()

    state_dir = tmp_path
    staged = state_dir / "eudrs_u" / "staged_registry_tree"
    src_vision = repo / "polymath/registry/eudrs_u/vision"
    dst_vision = staged / "polymath/registry/eudrs_u/vision"
    if dst_vision.exists():
        shutil.rmtree(dst_vision)
    dst_vision.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_vision, dst_vision)

    rid = _RUN_IDS[0]
    run_path = staged / f"polymath/registry/eudrs_u/vision/perception/runs/sha256_{_hex64(rid)}.vision_perception_run_manifest_v1.json"
    run_obj = gcj1_loads_and_verify_canonical(run_path.read_bytes())
    assert isinstance(run_obj, dict)
    rep0 = run_obj["frame_reports"][0]["report_ref"]
    rep0_path = staged / rep0["artifact_relpath"]
    assert rep0_path.exists()
    rep0_path.unlink()  # remove one referenced artifact

    with pytest.raises(OmegaV18Error):
        verify(state_dir, run_manifest_path=run_path)
