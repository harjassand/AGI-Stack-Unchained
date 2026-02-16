from __future__ import annotations

import json
from pathlib import Path

from genesis.capsules import enforce_budget_strings, validate_capsule
from genesis.capsules.receipt import verify_receipt

ROOT = Path(__file__).resolve().parents[2]


def _specpack_path(*parts: str) -> Path:
    primary = ROOT.joinpath(*parts)
    if primary.exists():
        return primary
    return ROOT / "genesis" / "tests" / "fixtures" / "specpack" / Path(*parts)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_validate_seed_capsule():
    capsule = load_json(ROOT / "genesis" / "capsules" / "seed_capsule.json")
    ok, err = validate_capsule(capsule)
    assert ok, err
    ok, err = enforce_budget_strings(capsule)
    assert ok, err


def test_budget_string_enforcement():
    capsule = load_json(ROOT / "genesis" / "capsules" / "seed_capsule.json")
    capsule["budget_bid"]["alpha_bid"] = 0.1
    ok, err = enforce_budget_strings(capsule)
    assert not ok
    assert "alpha_bid" in err


def test_verify_receipt_passes():
    receipt = load_json(_specpack_path("receipt_examples", "pass_receipt.json"))
    capsule = load_json(_specpack_path("examples", "algorithm.capsule.json"))
    ok, err = verify_receipt(receipt, capsule, receipt.get("epoch_id", ""))
    assert ok, err


def test_verify_receipt_mismatch():
    receipt = load_json(_specpack_path("receipt_examples", "pass_receipt.json"))
    capsule = load_json(_specpack_path("examples", "algorithm.capsule.json"))
    capsule["capsule_id"] = "00000000-0000-0000-0000-000000000000"
    ok, _ = verify_receipt(receipt, capsule, receipt.get("epoch_id", ""))
    assert not ok
