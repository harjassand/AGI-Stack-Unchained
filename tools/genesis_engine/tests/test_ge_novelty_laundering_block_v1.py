from __future__ import annotations

from pathlib import Path

from tools.genesis_engine.sh1_behavior_sig_v1 import build_behavior_signature, novelty_bits
from tools.genesis_engine.sh1_xs_v1 import load_ge_config


def _sha(char: str) -> str:
    return f"sha256:{char * 64}"


def _receipt(ccap_id: str) -> dict:
    return {
        "schema_version": "ccap_receipt_v1",
        "ccap_id": ccap_id,
        "base_tree_id": _sha("a"),
        "applied_tree_id": _sha("b"),
        "realized_out_id": _sha("c"),
        "ek_id": _sha("d"),
        "op_pool_id": _sha("e"),
        "auth_hash": _sha("f"),
        "determinism_check": "PASS",
        "eval_status": "PASS",
        "decision": "REJECT",
        "cost_vector": {
            "cpu_ms": 50,
            "wall_ms": 60,
            "mem_mb": 5,
            "disk_mb": 5,
            "fds": 5,
            "procs": 5,
            "threads": 5,
        },
        "logs_hash": _sha("1"),
    }


def test_ge_novelty_laundering_block_v1() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    ge_config = load_ge_config(repo_root / "tools" / "genesis_engine" / "config" / "ge_config_v1.json")

    # Different patch sizes are intentionally out-of-band and must not influence behavior signatures.
    _patch_size_a = 128
    _patch_size_b = 8192

    sig_a = build_behavior_signature(
        ge_config=ge_config,
        receipt_payload=_receipt(_sha("2")),
        refutation_code="",
    )
    sig_b = build_behavior_signature(
        ge_config=ge_config,
        receipt_payload=_receipt(_sha("3")),
        refutation_code="",
    )

    assert sig_a["beh_id"] == sig_b["beh_id"]

    reservoir = [_sha("9")]
    novelty_a = novelty_bits(beh_id=str(sig_a["beh_id"]), reservoir_beh_ids=reservoir)
    novelty_b = novelty_bits(beh_id=str(sig_b["beh_id"]), reservoir_beh_ids=reservoir)
    assert novelty_a == novelty_b
