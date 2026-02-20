#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import load_canon_dict, validate_schema


def _latest(path: Path, pattern: str) -> Path:
    rows = sorted(path.glob(pattern), key=lambda p: p.as_posix())
    if not rows:
        raise FileNotFoundError(f"missing {pattern} under {path}")
    return rows[-1]


def _require_sha(value: Any, field: str) -> str:
    text = str(value).strip()
    if not text.startswith("sha256:") or len(text.split(":", 1)[1]) != 64:
        raise ValueError(f"invalid {field}")
    return text


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="generate_phase4_audit_bundle_v1")
    ap.add_argument(
        "--state_dir",
        default="daemon/rsi_knowledge_transpiler_v1/state",
        help="Transpiler campaign state dir (default: daemon/rsi_knowledge_transpiler_v1/state)",
    )
    ap.add_argument(
        "--out",
        default="runs/PHASE4_AUDIT_BUNDLE_v1.json",
        help="Output audit bundle path",
    )
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    state_dir = (REPO_ROOT / str(args.state_dir)).resolve()
    out_path = (REPO_ROOT / str(args.out)).resolve()

    promotion_dir = state_dir / "promotion"
    bundle_path = _latest(promotion_dir, "sha256_*.omega_promotion_bundle_native_transpiler_v1_1.json")
    bundle = load_canon_dict(bundle_path)
    validate_schema(bundle, "omega_promotion_bundle_native_transpiler_v1_1")

    source_merkle_hash = _require_sha(bundle.get("source_merkle_hash"), "source_merkle_hash")
    build_proof_hash = _require_sha(bundle.get("build_proof_hash"), "build_proof_hash")

    source_merkle_path = state_dir / "native" / "src_merkle" / f"sha256_{source_merkle_hash.split(':', 1)[1]}.native_src_merkle_v1.json"
    build_proof_path = state_dir / "native" / "build" / f"sha256_{build_proof_hash.split(':', 1)[1]}.native_build_proof_v1.json"
    if not source_merkle_path.exists() or not build_proof_path.exists():
        raise FileNotFoundError("missing source merkle or build proof artifact")

    source_merkle = load_canon_dict(source_merkle_path)
    build_proof = load_canon_dict(build_proof_path)
    validate_schema(source_merkle, "native_src_merkle_v1")
    validate_schema(build_proof, "native_build_proof_v1")

    sip_knowledge_artifact_hash = _require_sha(bundle.get("sip_knowledge_artifact_hash"), "sip_knowledge_artifact_hash")
    sip_empirical_evidence_hash = _require_sha(bundle.get("sip_empirical_evidence_hash"), "sip_empirical_evidence_hash")
    runtime_contract_hash = _require_sha(bundle.get("runtime_contract_hash"), "runtime_contract_hash")
    native_binary_hash = _require_sha(bundle.get("native_binary_hash"), "native_binary_hash")

    payload = {
        "schema_version": "PHASE4_AUDIT_BUNDLE_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sip_dataset_hash": sip_knowledge_artifact_hash,
        "source_merkle_root": _require_sha(source_merkle.get("source_merkle_root"), "source_merkle_root"),
        "toolchain_root_hash": _require_sha(build_proof.get("rust_toolchain_hash"), "rust_toolchain_hash"),
        "runtime_contract_hash": runtime_contract_hash,
        "binary_hash": native_binary_hash,
        "build_proof_hash": build_proof_hash,
        "sip_empirical_evidence": {
            "sip_knowledge_artifact_hash": sip_knowledge_artifact_hash,
            "sip_empirical_evidence_hash": sip_empirical_evidence_hash,
        },
        "reproducible_build_merkle_proof": {
            "source_merkle_hash": source_merkle_hash,
            "build_proof_hash": build_proof_hash,
        },
        "native_binary_hash": native_binary_hash,
    }
    validate_schema(payload, "phase4_audit_bundle_v1")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, payload)
    print(str(out_path))


if __name__ == "__main__":
    main()
