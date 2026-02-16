"""Verifier for RSI flywheel v2.0 runs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, loads, sha256_prefixed
from .verify_rsi_demon_v6 import verify as verify_attempt


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _run_attempt_verifier(attempt_dir: Path) -> tuple[str, str]:
    try:
        verify_attempt(attempt_dir)
    except Exception as exc:  # noqa: BLE001
        reason = str(exc) if str(exc) else "unknown"
        return "INVALID", reason
    return "VALID", ""


def _load_flywheel_pack_used(state_dir: Path) -> dict[str, Any]:
    pack_path = state_dir / "flywheel" / "flywheel_pack_used.json"
    if not pack_path.exists():
        _fail("FLYWHEEL_PACK_NOT_PINNED")
    payload = load_canon_json(pack_path)
    if payload.get("schema") != "rsi_real_flywheel_pack_v1" or int(payload.get("schema_version", 0)) != 1:
        _fail("FLYWHEEL_PACK_NOT_PINNED")
    return payload


def _verify_pack_pinning(state_dir: Path, pack_used: dict[str, Any]) -> None:
    source_path = _repo_root() / "campaigns" / "rsi_real_flywheel_v2_0" / "rsi_real_flywheel_pack_v1.json"
    if source_path.exists():
        source = load_canon_json(source_path)
        if sha256_prefixed(canon_bytes(source)) != sha256_prefixed(canon_bytes(pack_used)):
            _fail("FLYWHEEL_PACK_NOT_PINNED")


def _load_ledger(state_dir: Path) -> list[dict[str, Any]]:
    ledger_path = state_dir / "flywheel" / "flywheel_ledger_v1.jsonl"
    if not ledger_path.exists():
        _fail("FLYWHEEL_LEDGER_INVALID")
    entries: list[dict[str, Any]] = []
    for raw in ledger_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        payload = loads(raw)
        if canon_bytes(payload).decode("utf-8") != raw:
            _fail("FLYWHEEL_LEDGER_INVALID")
        if not isinstance(payload, dict):
            _fail("FLYWHEEL_LEDGER_INVALID")
        entries.append(payload)
    return entries


def _verify_ledger(entries: list[dict[str, Any]], state_dir: Path) -> None:
    expected_index = 1
    seen_dirs: set[str] = set()
    for entry in entries:
        if entry.get("schema") != "flywheel_event_v1" or int(entry.get("schema_version", 0)) != 1:
            _fail("FLYWHEEL_LEDGER_INVALID")
        if int(entry.get("attempt_index", 0)) != expected_index:
            _fail("FLYWHEEL_LEDGER_INVALID")
        attempt_dir = entry.get("attempt_dir")
        if attempt_dir != f"attempts/attempt_{expected_index:04d}":
            _fail("FLYWHEEL_LEDGER_INVALID")
        if attempt_dir in seen_dirs:
            _fail("FLYWHEEL_LEDGER_INVALID")
        seen_dirs.add(attempt_dir)
        attempt_path = state_dir / attempt_dir
        if not attempt_path.exists():
            _fail("FLYWHEEL_LEDGER_INVALID")
        expected_index += 1

    attempts_root = state_dir / "attempts"
    if attempts_root.exists():
        for path in attempts_root.iterdir():
            if path.is_dir() and path.name.startswith("attempt_"):
                rel = f"attempts/{path.name}"
                if rel not in seen_dirs:
                    _fail("FLYWHEEL_LEDGER_INVALID")


def _verify_attempt_chain(entries: list[dict[str, Any]], state_dir: Path) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for entry in entries:
        attempt_dir = state_dir / str(entry.get("attempt_dir"))
        verdict, reason = _run_attempt_verifier(attempt_dir)
        if verdict != entry.get("verifier_verdict"):
            _fail("FLYWHEEL_ATTEMPT_VERDICT_MISMATCH")
        if verdict == "INVALID":
            if reason != entry.get("verifier_reason"):
                _fail("FLYWHEEL_ATTEMPT_VERDICT_MISMATCH")
        else:
            if str(entry.get("verifier_reason")):
                _fail("FLYWHEEL_ATTEMPT_VERDICT_MISMATCH")
        results.append((verdict, reason))
    return results


def _verify_prior_reasons(entries: list[dict[str, Any]], results: list[tuple[str, str]], state_dir: Path) -> None:
    for idx in range(1, len(entries)):
        attempt_index = idx + 1
        manifest_path = state_dir / "attempts" / f"attempt_{attempt_index:04d}" / "autonomy" / "metabolism_v1" / "autonomy_manifest_v2.json"
        if not manifest_path.exists():
            _fail("FLYWHEEL_PRIOR_REASON_MISMATCH")
        manifest = load_canon_json(manifest_path)
        if int(manifest.get("prior_attempt_index", -1)) != attempt_index - 1:
            _fail("FLYWHEEL_PRIOR_REASON_MISMATCH")
        prior_reason = results[idx - 1][1]
        if str(manifest.get("prior_verifier_reason", "")) != prior_reason:
            _fail("FLYWHEEL_PRIOR_REASON_MISMATCH")


def _verify_termination(entries: list[dict[str, Any]], results: list[tuple[str, str]], state_dir: Path) -> None:
    receipt_path = state_dir / "flywheel" / "rsi_flywheel_receipt_v1.json"
    if not receipt_path.exists():
        _fail("FLYWHEEL_TERMINATION_INVALID")
    receipt = load_canon_json(receipt_path)

    verdict = receipt.get("verdict")
    if verdict not in {"VALID", "INVALID"}:
        _fail("FLYWHEEL_TERMINATION_INVALID")

    attempts_executed = int(receipt.get("attempts_executed", -1))
    if attempts_executed != len(entries):
        _fail("FLYWHEEL_TERMINATION_INVALID")

    if "VALID" in [verdict for verdict, _ in results]:
        if results[-1][0] != "VALID":
            _fail("FLYWHEEL_TERMINATION_INVALID")
        if verdict != "VALID":
            _fail("FLYWHEEL_TERMINATION_INVALID")
        winning_index = int(receipt.get("winning_attempt_index", -1))
        if winning_index != attempts_executed:
            _fail("FLYWHEEL_TERMINATION_INVALID")
        winning_dir = receipt.get("winning_attempt_dir")
        if winning_dir != f"attempts/attempt_{winning_index:04d}":
            _fail("FLYWHEEL_TERMINATION_INVALID")

        winning = receipt.get("winning") if isinstance(receipt.get("winning"), dict) else None
        if not isinstance(winning, dict):
            _fail("FLYWHEEL_TERMINATION_INVALID")

        attempt_receipt_path = (
            state_dir
            / "attempts"
            / f"attempt_{winning_index:04d}"
            / "epochs"
            / "epoch_6"
            / "diagnostics"
            / "rsi_demon_receipt_v6.json"
        )
        if not attempt_receipt_path.exists():
            _fail("FLYWHEEL_TERMINATION_INVALID")
        attempt_receipt = load_canon_json(attempt_receipt_path)
        metab = attempt_receipt.get("metabolism_v1") if isinstance(attempt_receipt.get("metabolism_v1"), dict) else None
        if not isinstance(metab, dict):
            _fail("FLYWHEEL_TERMINATION_INVALID")
        if winning.get("active_patch_id") != metab.get("active_patch_id"):
            _fail("FLYWHEEL_TERMINATION_INVALID")
        if winning.get("rho_met") != metab.get("rho_met"):
            _fail("FLYWHEEL_TERMINATION_INVALID")
    else:
        if verdict != "INVALID":
            _fail("FLYWHEEL_TERMINATION_INVALID")
        if int(receipt.get("winning_attempt_index", -1)) != 0:
            _fail("FLYWHEEL_TERMINATION_INVALID")
        if receipt.get("winning_attempt_dir") != "":
            _fail("FLYWHEEL_TERMINATION_INVALID")
        winning = receipt.get("winning") if isinstance(receipt.get("winning"), dict) else None
        if not isinstance(winning, dict):
            _fail("FLYWHEEL_TERMINATION_INVALID")
        if winning.get("active_patch_id") != "":
            _fail("FLYWHEEL_TERMINATION_INVALID")


def verify(state_dir: Path) -> None:
    pack_used = _load_flywheel_pack_used(state_dir)
    _verify_pack_pinning(state_dir, pack_used)

    entries = _load_ledger(state_dir)
    _verify_ledger(entries, state_dir)

    results = _verify_attempt_chain(entries, state_dir)
    _verify_prior_reasons(entries, results, state_dir)
    _verify_termination(entries, results, state_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify RSI flywheel v2.0 run")
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()
    try:
        verify(Path(args.state_dir))
    except Exception as exc:  # noqa: BLE001
        reason = str(exc) if str(exc) else "unknown"
        print(f"INVALID: {reason}")
        return
    print("VALID")


if __name__ == "__main__":
    main()
