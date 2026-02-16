from __future__ import annotations

import json
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_count_ge_sh1_artifacts_empty_state(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    got = runner._count_ge_sh1_artifacts(run_dir)
    assert got == {"ge_dispatch_u64": 0, "ccap_receipts_u64": 0}


def test_count_ge_sh1_artifacts_filters_to_ge_and_dedupes_ccap_ids(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    state_dir = run_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    ge_dispatch = state_dir / "dispatch" / "a0"
    non_ge_dispatch = state_dir / "dispatch" / "a1"

    _write_json(
        ge_dispatch / ("sha256_" + ("1" * 64) + ".omega_dispatch_receipt_v1.json"),
        {
            "schema_version": "omega_dispatch_receipt_v1",
            "tick_u64": 1,
            "campaign_id": "rsi_ge_symbiotic_optimizer_sh1_v0_1",
        },
    )
    _write_json(
        non_ge_dispatch / ("sha256_" + ("2" * 64) + ".omega_dispatch_receipt_v1.json"),
        {
            "schema_version": "omega_dispatch_receipt_v1",
            "tick_u64": 1,
            "campaign_id": "rsi_sas_code_v12_0",
        },
    )

    ccap_payload = {
        "schema_version": "ccap_receipt_v1",
        "ccap_id": "sha256:" + ("a" * 64),
    }
    _write_json(ge_dispatch / "verifier" / "ccap_receipt_v1.json", ccap_payload)
    _write_json(ge_dispatch / "verifier" / ("sha256_" + ("3" * 64) + ".ccap_receipt_v1.json"), ccap_payload)
    _write_json(
        non_ge_dispatch / "verifier" / "ccap_receipt_v1.json",
        {
            "schema_version": "ccap_receipt_v1",
            "ccap_id": "sha256:" + ("b" * 64),
        },
    )

    got = runner._count_ge_sh1_artifacts(run_dir)
    assert got["ge_dispatch_u64"] == 1
    assert got["ccap_receipts_u64"] == 1
