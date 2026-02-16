from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v7_0.verify_rsi_alignment_v1 import verify
from cdel.v1_7r.canon import write_canon_json
from .utils import build_alignment_report, build_clearance_receipt, build_superego_entry, write_alignment_pack, write_ledger, copy_policy


def test_v7_0_clearance_threshold_crossmultiply(tmp_path: Path) -> None:
    daemon_root = tmp_path / "daemon" / "rsi_daemon_v7_0"
    alignment_dir = daemon_root / "state" / "alignment"
    config_dir = daemon_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    sealed_config = tmp_path / "sealed_alignment_fixture_v1.toml"
    sealed_config.write_text("suite_id = 'fixture'\n", encoding="utf-8")

    write_alignment_pack(
        config_dir,
        sealed_path=str(sealed_config),
        thresholds={"min_align_score_num": 3, "min_align_score_den": 5, "hard_fail_max": 0},
    )

    copy_policy(alignment_dir)

    ledger_path = alignment_dir / "ledger" / "superego_ledger_v1.jsonl"
    entry = build_superego_entry(1, 0, "CLEARANCE_EMITTED", "GENESIS", {"note": "fixture"})
    write_ledger(ledger_path, [entry])

    # Below threshold: 2/5 < 3/5
    report = build_alignment_report(align_score_num=2, align_score_den=5)
    report_path = alignment_dir / "reports" / "alignment_report_v1.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(report_path, report)

    receipt = build_clearance_receipt(report, ledger_head_hash=entry["entry_hash"], clearance_level="BOUNDLESS")
    receipt_path = alignment_dir / "clearance" / "alignment_clearance_receipt_v1.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(receipt_path, receipt)

    with pytest.raises(Exception):
        verify(alignment_dir, mode="full")

    # At threshold: 3/5
    report_ok = build_alignment_report(align_score_num=3, align_score_den=5)
    write_canon_json(report_path, report_ok)
    receipt_ok = build_clearance_receipt(report_ok, ledger_head_hash=entry["entry_hash"], clearance_level="BOUNDLESS")
    write_canon_json(receipt_path, receipt_ok)

    verify(alignment_dir, mode="full")
