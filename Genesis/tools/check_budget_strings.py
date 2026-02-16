#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "examples"
MOCK_CAPSULE = EXAMPLES_DIR / "mock_pass.capsule.json"
MOCK_CDEL = ROOT / "tools" / "mock_cdel.py"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def ensure_string(value, label: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")


def check_capsule_budgets(path: Path) -> None:
    capsule = load_json(path)
    bid = capsule.get("budget_bid") or {}
    ensure_string(bid.get("alpha_bid"), f"{path.name}:budget_bid.alpha_bid")
    privacy = bid.get("privacy_bid") or {}
    ensure_string(privacy.get("epsilon"), f"{path.name}:budget_bid.privacy_bid.epsilon")
    ensure_string(privacy.get("delta"), f"{path.name}:budget_bid.privacy_bid.delta")


def check_mock_receipt() -> None:
    capsule = load_json(MOCK_CAPSULE)
    request = {
        "epoch_id": "epoch-1",
        "capsule": capsule,
        "bid": capsule.get("budget_bid"),
    }
    proc = subprocess.run(
        [sys.executable, str(MOCK_CDEL), "--mode", "stdin"],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError(f"mock_cdel failed: {proc.stderr.strip()}")
    response = json.loads(proc.stdout)
    if response.get("result") != "PASS":
        raise ValueError("mock_cdel did not return PASS for mock_pass.capsule.json")
    receipt = response.get("receipt") or {}
    budgets = receipt.get("budgets_spent") or {}
    ensure_string(budgets.get("alpha_spent"), "mock_receipt.budgets_spent.alpha_spent")
    privacy = budgets.get("privacy_spent") or {}
    ensure_string(privacy.get("epsilon_spent"), "mock_receipt.budgets_spent.privacy_spent.epsilon_spent")
    ensure_string(privacy.get("delta_spent"), "mock_receipt.budgets_spent.privacy_spent.delta_spent")


def main() -> int:
    for path in sorted(EXAMPLES_DIR.glob("*.capsule.json")):
        check_capsule_budgets(path)
    check_mock_receipt()
    print("budget string check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
