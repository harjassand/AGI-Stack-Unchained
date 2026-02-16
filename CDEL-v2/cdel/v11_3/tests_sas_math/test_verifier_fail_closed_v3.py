from __future__ import annotations

import pytest
from pathlib import Path

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v11_3.verify_rsi_sas_math_v3 import verify

from .utils import build_state


def test_statement_forbidden_import_rejected(tmp_path: Path) -> None:
    state = build_state(tmp_path, binder_name="importStd")
    with pytest.raises(Exception) as exc:
        verify(state.state_dir, mode="full")
    assert "FORBIDDEN_TOKEN_STATEMENT" in str(exc.value)


def test_verifier_fail_closed_duplicate_fingerprint(tmp_path: Path) -> None:
    state = build_state(tmp_path)
    bundle_path = next((state.state_dir / "conjectures" / "bundles").glob("sha256_*.sas_conjecture_bundle_v3.json"))
    bundle = load_canon_json(bundle_path)
    bundle["conjectures"].append(bundle["conjectures"][0])
    bundle_hash = sha256_prefixed(canon_bytes({k: v for k, v in bundle.items() if k != "bundle_id"}))
    bundle["bundle_id"] = bundle_hash
    new_path = bundle_path.parent / f"sha256_{bundle_hash.split(':',1)[1]}.sas_conjecture_bundle_v3.json"
    if new_path != bundle_path:
        bundle_path.unlink()
    write_canon_json(new_path, bundle)
    receipt_path = next((state.state_dir / "conjectures" / "receipts").glob("sha256_*.sas_conjecture_gen_receipt_v3.json"))
    receipt = load_canon_json(receipt_path)
    receipt["bundle_hash"] = bundle_hash
    receipt_hash = sha256_prefixed(canon_bytes({k: v for k, v in receipt.items() if k != "receipt_id"}))
    receipt["receipt_id"] = receipt_hash
    write_canon_json(receipt_path, receipt)
    with pytest.raises(Exception) as exc:
        verify(state.state_dir, mode="full")
    assert "DUPLICATE_FINGERPRINT_IN_BUNDLE" in str(exc.value)


def test_depth_gate_blocks_one_liner(tmp_path: Path) -> None:
    state = build_state(tmp_path, candidate_proof_text="by rfl\n")
    with pytest.raises(Exception) as exc:
        verify(state.state_dir, mode="full")
    assert "DEPTH_GATE_VIOLATION" in str(exc.value)
