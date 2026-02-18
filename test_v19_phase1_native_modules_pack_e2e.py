from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from orchestrator.omega_v19_0.coordinator_v1 import run_tick


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_v19_phase1_native_modules_tick_smoke(tmp_path: Path) -> None:
    pack = _repo_root() / "campaigns" / "rsi_omega_daemon_v19_0_phase1_native_modules_v1" / "rsi_omega_daemon_pack_v1.json"
    assert pack.exists() and pack.is_file()

    prev_mode = os.environ.get("OMEGA_META_CORE_ACTIVATION_MODE")
    prev_allow = os.environ.get("OMEGA_ALLOW_SIMULATE_ACTIVATION")
    prev_native = os.environ.get("OMEGA_NATIVE_CANON_BYTES")
    os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = "simulate"
    os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = "1"
    os.environ["OMEGA_NATIVE_CANON_BYTES"] = "1"
    try:
        out_dir_1 = tmp_path / "tick_0001"
        run_tick(campaign_pack=pack, out_dir=out_dir_1, tick_u64=1, prev_state_dir=None)
        state_dir_1 = out_dir_1 / "daemon" / "rsi_omega_daemon_v19_0" / "state"

        out_dir_2 = tmp_path / "tick_0002"
        run_tick(campaign_pack=pack, out_dir=out_dir_2, tick_u64=2, prev_state_dir=state_dir_1)
    finally:
        if prev_mode is None:
            os.environ.pop("OMEGA_META_CORE_ACTIVATION_MODE", None)
        else:
            os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = prev_mode
        if prev_allow is None:
            os.environ.pop("OMEGA_ALLOW_SIMULATE_ACTIVATION", None)
        else:
            os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = prev_allow
        if prev_native is None:
            os.environ.pop("OMEGA_NATIVE_CANON_BYTES", None)
        else:
            os.environ["OMEGA_NATIVE_CANON_BYTES"] = prev_native

    state_dir = out_dir_1 / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    dispatch_root = state_dir / "dispatch"
    dispatch_dirs = sorted([p for p in dispatch_root.iterdir() if p.is_dir()])
    assert dispatch_dirs, "missing dispatch dir"
    dispatch_dir = dispatch_dirs[-1]

    subverifier_paths = sorted(dispatch_dir.rglob("*.omega_subverifier_receipt_v1.json"))
    assert subverifier_paths, "missing subverifier receipt"
    subverifier = _load(subverifier_paths[-1])
    assert (subverifier.get("result") or {}).get("status") == "VALID"

    promotion_paths = sorted((dispatch_dir / "promotion").glob("*.omega_promotion_receipt_v1.json"))
    assert promotion_paths, "missing promotion receipt"
    promotion = _load(promotion_paths[-1])
    assert (promotion.get("result") or {}).get("status") == "PROMOTED"
    assert promotion.get("native_module")
    assert promotion["native_module"]["op_id"] == "omega_kernel_canon_bytes_v1"

    activation_paths = sorted((dispatch_dir / "activation").glob("*.omega_activation_receipt_v1.json"))
    assert activation_paths, "missing activation receipt"
    activation = _load(activation_paths[-1])
    assert activation.get("activation_success") is True
    assert activation.get("native_activation_gate_result") == "PASS"
    assert activation.get("native_gate_reason") == "NATIVE_GATE_PASS"
    assert activation.get("native_module")
    assert activation["native_module"]["binary_sha256"] == promotion["native_module"]["binary_sha256"]

    # Tick 2 should exercise the native hotpath and emit deterministic runtime stats
    # linked into the tick trace chain.
    state_dir_2 = out_dir_2 / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    stats_paths = sorted((state_dir_2 / "ledger" / "native").glob("sha256_*.omega_native_runtime_stats_v1.json"))
    assert stats_paths, "missing omega_native_runtime_stats_v1"
    stats = _load(stats_paths[-1])
    assert stats.get("schema_version") == "omega_native_runtime_stats_v1"
    ops = stats.get("ops")
    assert isinstance(ops, list) and ops, "missing ops rows"
    rows = [row for row in ops if isinstance(row, dict) and row.get("op_id") == "omega_kernel_canon_bytes_v1"]
    assert rows, "missing canon_bytes op stats"
    assert int(rows[0].get("native_returned_u64", 0)) > 0
