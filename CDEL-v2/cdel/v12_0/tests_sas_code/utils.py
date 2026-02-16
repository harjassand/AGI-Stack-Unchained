from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from orchestrator.sas_code_v12_0.controller_v1 import run_sas_code


@dataclass
class SASCodeState:
    agi_root: Path
    sas_root: Path
    state_dir: Path
    config_dir: Path


def build_state(tmp_path: Path) -> SASCodeState:
    agi_root = tmp_path / "agi_root"
    sas_root = agi_root / "daemon" / "rsi_sas_code_v12_0"
    state_dir = sas_root / "state"
    config_dir = sas_root / "config"
    control_dir = state_dir / "control"
    control_dir.mkdir(parents=True, exist_ok=True)

    # enable flags
    (control_dir / "ENABLE_RESEARCH").write_text("enable", encoding="utf-8")
    (control_dir / "ENABLE_SAS_CODE").write_text("enable", encoding="utf-8")

    # lease
    repo_root = Path(__file__).resolve().parents[4]
    lease_src = repo_root / "campaigns" / "rsi_sas_code_v12_0" / "sas_code_lease_token_v1.json"
    (control_dir / "SAS_CODE_LEASE.json").write_bytes(lease_src.read_bytes())

    pack_path = repo_root / "campaigns" / "rsi_sas_code_v12_0" / "rsi_sas_code_pack_v1.json"

    old_agi_root = os.environ.get("AGI_ROOT")
    os.environ["AGI_ROOT"] = str(agi_root)
    try:
        run_sas_code(sas_code_root=sas_root, pack_path=pack_path)
    finally:
        if old_agi_root is None:
            os.environ.pop("AGI_ROOT", None)
        else:
            os.environ["AGI_ROOT"] = old_agi_root

    return SASCodeState(agi_root=agi_root, sas_root=sas_root, state_dir=state_dir, config_dir=config_dir)


def rewrite_proof_and_receipts(state: SASCodeState, new_proof_text: str) -> None:
    from cdel.v1_7r.canon import load_canon_json, write_canon_json, sha256_prefixed, canon_bytes
    from cdel.v8_0.math_toolchain import load_toolchain_manifest
    from cdel.v8_0.sealed_proofcheck import compute_sealed_receipt_hash
    from cdel.v12_0.sas_code_proof_task_v1 import sealed_proof_check_receipt, compute_attempt_receipt_hash

    promo_dir = state.state_dir / "promotion"
    promo_path = next(promo_dir.glob("sha256_*.sas_code_promotion_bundle_v1.json"))
    promo = load_canon_json(promo_path)

    attempt_hash = promo["candidate_attempt_receipt_sha256"]
    receipt_dir = state.state_dir / "code" / "attempts" / "receipts"
    attempt_path = receipt_dir / f"sha256_{attempt_hash.split(':',1)[1]}.sas_code_attempt_receipt_v1.json"
    attempt = load_canon_json(attempt_path)

    proof_bytes = new_proof_text.encode("utf-8")
    new_proof_hash = sha256_prefixed(proof_bytes)
    proof_dir = state.state_dir / "code" / "attempts" / "proofs"
    new_proof_path = proof_dir / f"sha256_{new_proof_hash.split(':',1)[1]}.proof.lean"
    new_proof_path.write_bytes(proof_bytes)

    old_proof_hash = attempt.get("proof_artifact_hash")
    if isinstance(old_proof_hash, str):
        old_proof_path = proof_dir / f"sha256_{old_proof_hash.split(':',1)[1]}.proof.lean"
        if old_proof_path.exists():
            old_proof_path.unlink()

    preamble_hash = attempt.get("lean_preamble_sha256")
    preamble_relpath = attempt.get("lean_preamble_relpath") or ""
    repo_root = Path(__file__).resolve().parents[4]
    preamble_path = repo_root / preamble_relpath
    toolchain_path = state.config_dir / "sas_code_toolchain_manifest_lean4_v1.json"
    toolchain_manifest = load_toolchain_manifest(toolchain_path)
    work_dir = state.state_dir / "code" / "attempts" / "work" / "attempts" / f"sha256:{attempt.get('attempt_id').split(':',1)[1]}"
    sealed = sealed_proof_check_receipt(
        toolchain_manifest=toolchain_manifest,
        problem_id=str(attempt.get("problem_id")),
        attempt_id=str(attempt.get("attempt_id")),
        proof_text=new_proof_text,
        lean_preamble_path=preamble_path,
        lean_preamble_sha256=str(preamble_hash) if preamble_hash else None,
        work_dir=work_dir,
    )
    sealed_hash = compute_sealed_receipt_hash(sealed)
    sealed_dir = state.state_dir / "code" / "attempts" / "sealed"
    sealed_path = sealed_dir / f"sha256_{sealed_hash.split(':',1)[1]}.sealed_proof_check_receipt_v1.json"
    write_canon_json(sealed_path, sealed)

    old_sealed_hash = attempt.get("sealed_proof_check_receipt_hash")
    if isinstance(old_sealed_hash, str):
        old_sealed_path = sealed_dir / f"sha256_{old_sealed_hash.split(':',1)[1]}.sealed_proof_check_receipt_v1.json"
        if old_sealed_path.exists():
            old_sealed_path.unlink()

    attempt["proof_artifact_hash"] = new_proof_hash
    attempt["sealed_proof_check_receipt_hash"] = sealed_hash
    attempt["result"] = sealed.get("result")
    attempt["stdout_hash"] = sealed.get("stdout_hash")
    attempt["stderr_hash"] = sealed.get("stderr_hash")

    new_attempt_hash = compute_attempt_receipt_hash(attempt)
    new_attempt_path = receipt_dir / f"sha256_{new_attempt_hash.split(':',1)[1]}.sas_code_attempt_receipt_v1.json"
    write_canon_json(new_attempt_path, attempt)
    if attempt_path.exists():
        attempt_path.unlink()

    promo["candidate_attempt_receipt_sha256"] = new_attempt_hash
    promo["sealed_proof_receipt_sha256"] = sealed_hash
    promo["bundle_id"] = sha256_prefixed(canon_bytes({k: v for k, v in promo.items() if k != "bundle_id"}))

    new_promo_hash = sha256_prefixed(canon_bytes(promo))
    new_promo_path = promo_dir / f"sha256_{new_promo_hash.split(':',1)[1]}.sas_code_promotion_bundle_v1.json"
    write_canon_json(new_promo_path, promo)
    if promo_path.exists():
        promo_path.unlink()
