from __future__ import annotations

import json
import os
from pathlib import Path

from cdel.v18_0.tests_omega_daemon.utils import latest_file, repo_root, run_tick_with_pack


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase1_native_modules_pack_tick_smoke(tmp_path: Path) -> None:
    pack = repo_root() / "campaigns" / "rsi_omega_daemon_v18_0_phase1_native_modules_v1" / "rsi_omega_daemon_pack_v1.json"
    assert pack.exists() and pack.is_file()

    prev_native = os.environ.get("OMEGA_NATIVE_CANON_BYTES")
    os.environ["OMEGA_NATIVE_CANON_BYTES"] = "1"
    try:
        _result, state_dir_1 = run_tick_with_pack(tmp_path=tmp_path, campaign_pack=pack, tick_u64=1, prev_state_dir=None)
        _result, state_dir_2 = run_tick_with_pack(tmp_path=tmp_path, campaign_pack=pack, tick_u64=2, prev_state_dir=state_dir_1)
    finally:
        if prev_native is None:
            os.environ.pop("OMEGA_NATIVE_CANON_BYTES", None)
        else:
            os.environ["OMEGA_NATIVE_CANON_BYTES"] = prev_native

    dispatch_dirs = sorted([p for p in (state_dir_1 / "dispatch").iterdir() if p.is_dir()])
    assert dispatch_dirs, "missing dispatch dir"
    dispatch_dir = dispatch_dirs[-1]

    subverifier_paths = sorted(dispatch_dir.rglob("*.omega_subverifier_receipt_v1.json"))
    assert subverifier_paths, "missing subverifier receipt"
    subverifier = _load(subverifier_paths[-1])
    assert subverifier["result"]["status"] == "VALID"

    promotion_path = latest_file(dispatch_dir / "promotion", "*.omega_promotion_receipt_v1.json")
    promotion = _load(promotion_path)
    assert promotion["result"]["status"] == "PROMOTED"
    assert promotion.get("native_module")
    assert promotion["native_module"]["op_id"] == "omega_kernel_canon_bytes_v1"

    activation_path = latest_file(dispatch_dir / "activation", "*.omega_activation_receipt_v1.json")
    activation = _load(activation_path)
    assert activation["activation_success"] is True
    assert activation.get("native_activation_gate_result") == "PASS"
    assert activation.get("native_gate_reason") == "NATIVE_GATE_PASS"
    assert activation.get("native_module")
    assert activation["native_module"]["binary_sha256"] == promotion["native_module"]["binary_sha256"]

    stats_paths = sorted((state_dir_2 / "ledger" / "native").glob("sha256_*.omega_native_runtime_stats_v1.json"))
    assert stats_paths, "missing omega_native_runtime_stats_v1"
    stats = _load(stats_paths[-1])
    assert stats.get("schema_version") == "omega_native_runtime_stats_v1"
    ops = stats.get("ops")
    assert isinstance(ops, list) and ops, "missing ops rows"
    rows = [row for row in ops if isinstance(row, dict) and row.get("op_id") == "omega_kernel_canon_bytes_v1"]
    assert rows, "missing canon_bytes op stats"
    assert int(rows[0].get("native_returned_u64", 0)) > 0
