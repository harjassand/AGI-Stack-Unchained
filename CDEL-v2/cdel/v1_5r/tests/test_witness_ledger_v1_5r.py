from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_5r.canon import CanonError
from cdel.v1_5r.sr_cegar.witness import build_failure_witness
from cdel.v1_5r.sr_cegar.witness_ledger import (
    append_ledger_line,
    build_ledger_line,
    filter_witnesses_by_ledger,
    load_ledger_lines,
    verify_ledger_chain,
)


def _witness(epoch_id: str, family_id: str, inst_hash: str) -> dict:
    return build_failure_witness(
        epoch_id=epoch_id,
        subject="base",
        candidate_id=None,
        family_id=family_id,
        theta={},
        inst_hash=inst_hash,
        failure_kind="GOAL_FAIL",
        trace_hashes=[],
        shrink_proof_ref=None,
    )


def test_witness_ledger_chain_and_filter(tmp_path: Path) -> None:
    ledger_path = tmp_path / "witness_ledger_v1.jsonl"
    w1 = _witness("epoch0", "sha256:" + "0" * 64, "sha256:" + "1" * 64)
    w2 = _witness("epoch1", "sha256:" + "2" * 64, "sha256:" + "3" * 64)

    line1 = build_ledger_line(
        witness=w1,
        producing_receipt_hash="sha256:" + "4" * 64,
        origin_epoch_id="epoch0",
        prev_line_hash=None,
    )
    append_ledger_line(ledger_path, line1)

    line2 = build_ledger_line(
        witness=w2,
        producing_receipt_hash="sha256:" + "5" * 64,
        origin_epoch_id="epoch1",
        prev_line_hash=line1["line_hash"],
    )
    append_ledger_line(ledger_path, line2)

    lines = load_ledger_lines(ledger_path)
    head = verify_ledger_chain(lines)
    assert head == line2["line_hash"]

    filtered = filter_witnesses_by_ledger([w1, w2, _witness("epoch2", "sha256:" + "6" * 64, "sha256:" + "7" * 64)], lines)
    assert filtered == [w1, w2]


def test_witness_ledger_tamper_detected(tmp_path: Path) -> None:
    ledger_path = tmp_path / "witness_ledger_v1.jsonl"
    w1 = _witness("epoch0", "sha256:" + "0" * 64, "sha256:" + "1" * 64)
    line1 = build_ledger_line(
        witness=w1,
        producing_receipt_hash="sha256:" + "4" * 64,
        origin_epoch_id="epoch0",
        prev_line_hash=None,
    )
    append_ledger_line(ledger_path, line1)
    lines = load_ledger_lines(ledger_path)
    lines[0]["prev_line_hash"] = "sha256:" + "9" * 64
    with pytest.raises(CanonError):
        verify_ledger_chain(lines)
