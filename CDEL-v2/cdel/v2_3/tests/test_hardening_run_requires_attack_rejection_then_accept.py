from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import canon_bytes, load_canon_json, loads


def _load_canon_json_from_line(raw: str) -> dict:
    payload = loads(raw)
    if canon_bytes(payload).decode("utf-8") != raw:
        raise AssertionError("non-canonical jsonl")
    if not isinstance(payload, dict):
        raise AssertionError("invalid jsonl payload")
    return payload


def test_hardening_run_requires_attack_rejection_then_accept(hardening_run_dir: Path) -> None:
    ledger_path = hardening_run_dir / "ledger" / "hardening_ledger_v1.jsonl"
    entries = []
    for raw in ledger_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        entries.append(_load_canon_json_from_line(raw))

    rejects = []
    accepts = []
    for entry in entries:
        event = entry.get("event")
        if event == "HARDENING_PATCH_REJECT_V1":
            payload = entry.get("payload", {})
            if payload.get("reason") == "CSI_IMMUTABLE_CORE_TOUCH":
                rejects.append(entry)
        elif event == "HARDENING_PATCH_ACCEPT_V1":
            accepts.append(entry)

    assert rejects, "missing CSI_IMMUTABLE_CORE_TOUCH rejection"
    assert accepts, "missing accepted patch"

    first_reject_seq = min(int(entry.get("seq", 0)) for entry in rejects)
    assert any(int(entry.get("seq", 0)) > first_reject_seq for entry in accepts)

    receipt = load_canon_json(hardening_run_dir / "diagnostics" / "rsi_hardening_receipt_v1.json")
    assert receipt.get("verdict") == "VALID"
