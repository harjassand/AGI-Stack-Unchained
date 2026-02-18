from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import write_canon_json  # noqa: E402
from cdel.v19_0.continuity.common_v1 import ContinuityV19Error  # noqa: E402
from cdel.v19_0.omega_promoter_v1 import _verify_axis_bundle_gate  # noqa: E402


def _mk_ccap_bundle(*, ccap_hex: str, patch_hex: str) -> dict:
    ccap_id = f"sha256:{ccap_hex}"
    ccap_rel = f"ccap/sha256_{ccap_hex}.ccap_v1.json"
    patch_rel = f"ccap/blobs/sha256_{patch_hex}.patch"
    return {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": ccap_id,
        "ccap_relpath": ccap_rel,
        "patch_relpath": patch_rel,
        "touched_paths": [ccap_rel, patch_rel],
        "activation_key": ccap_id,
    }


def _write_min_ccap(path: Path, *, ccap_hex: str) -> None:
    # Axis-gate touched-path parsing only requires this file to exist.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{{\"schema_version\":\"ccap_v1\",\"stub\":\"{ccap_hex}\"}}\n", encoding="utf-8")


def test_v19_axis_gate_ccap_exempt_allows_without_axis_bundle(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    subrun_root = state_root / "subruns" / "subrun1"
    promo_dir = subrun_root / "promotion"
    promo_dir.mkdir(parents=True, exist_ok=True)

    ccap_hex = "1" * 64
    patch_hex = "2" * 64
    bundle = _mk_ccap_bundle(ccap_hex=ccap_hex, patch_hex=patch_hex)

    bundle_path = promo_dir / f"sha256_{'3'*64}.omega_promotion_bundle_ccap_v1.json"
    write_canon_json(bundle_path, bundle)

    _write_min_ccap(subrun_root / bundle["ccap_relpath"], ccap_hex=ccap_hex)
    patch_path = subrun_root / bundle["patch_relpath"]
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_bytes(
        (
            "diff --git a/orchestrator/omega_v19_0/coordinator_v1.py b/orchestrator/omega_v19_0/coordinator_v1.py\n"
            "--- a/orchestrator/omega_v19_0/coordinator_v1.py\n"
            "+++ b/orchestrator/omega_v19_0/coordinator_v1.py\n"
            "@@ -1 +1 @@\n"
            "-x\n"
            "+y\n"
        ).encode("utf-8")
    )

    out_promotion_dir = tmp_path / "dispatch_promotion"
    out_promotion_dir.mkdir(parents=True, exist_ok=True)

    _verify_axis_bundle_gate(bundle_obj=bundle, bundle_path=bundle_path, promotion_dir=out_promotion_dir)
    decision = (out_promotion_dir / "axis_gate_decision_v1.json").read_text(encoding="utf-8")
    assert "\"needs_axis_bundle_b\":false" in decision


def test_v19_axis_gate_ccap_non_exempt_requires_axis_bundle(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    subrun_root = state_root / "subruns" / "subrun2"
    promo_dir = subrun_root / "promotion"
    promo_dir.mkdir(parents=True, exist_ok=True)

    ccap_hex = "4" * 64
    patch_hex = "5" * 64
    bundle = _mk_ccap_bundle(ccap_hex=ccap_hex, patch_hex=patch_hex)
    bundle_path = promo_dir / f"sha256_{'6'*64}.omega_promotion_bundle_ccap_v1.json"
    write_canon_json(bundle_path, bundle)

    _write_min_ccap(subrun_root / bundle["ccap_relpath"], ccap_hex=ccap_hex)
    patch_path = subrun_root / bundle["patch_relpath"]
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_bytes(
        (
            "diff --git a/orchestrator/omega_v19_0/not_exempt.py b/orchestrator/omega_v19_0/not_exempt.py\n"
            "--- a/orchestrator/omega_v19_0/not_exempt.py\n"
            "+++ b/orchestrator/omega_v19_0/not_exempt.py\n"
            "@@ -1 +1 @@\n"
            "-x\n"
            "+y\n"
        ).encode("utf-8")
    )

    out_promotion_dir = tmp_path / "dispatch_promotion2"
    out_promotion_dir.mkdir(parents=True, exist_ok=True)

    try:
        _verify_axis_bundle_gate(bundle_obj=bundle, bundle_path=bundle_path, promotion_dir=out_promotion_dir)
    except ContinuityV19Error as exc:
        assert "MISSING_ARTIFACT" in str(exc)
    else:
        raise AssertionError("expected axis gate to fail without axis bundle for non-exempt governed CCAP patch")

    decision = (out_promotion_dir / "axis_gate_decision_v1.json").read_text(encoding="utf-8")
    assert "\"needs_axis_bundle_b\":true" in decision
    assert "\"axis_bundle_present_b\":false" in decision

