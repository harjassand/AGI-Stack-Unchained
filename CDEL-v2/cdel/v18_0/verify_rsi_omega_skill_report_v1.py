"""Verifier for analysis-only Omega legacy skill report campaigns."""

from __future__ import annotations

import argparse
from pathlib import Path

from .omega_common_v1 import canon_hash_obj, fail, load_canon_dict, validate_schema


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        fail("MODE_UNSUPPORTED")

    report_dir = state_dir / "reports"
    rows = sorted(report_dir.glob("sha256_*.omega_skill_report_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        fail("MISSING_STATE_INPUT")

    payload = load_canon_dict(rows[-1])
    validate_schema(payload, "omega_skill_report_v1")

    expected_hash = rows[-1].name.split(".", 1)[0].replace("sha256_", "sha256:")
    if canon_hash_obj(payload) != expected_hash:
        fail("NONDETERMINISTIC")

    plain_path = report_dir / "omega_skill_report_v1.json"
    if plain_path.exists() and plain_path.is_file():
        plain_payload = load_canon_dict(plain_path)
        validate_schema(plain_payload, "omega_skill_report_v1")
        if canon_hash_obj(plain_payload) != canon_hash_obj(payload):
            fail("NONDETERMINISTIC")

    return "VALID"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="verify_rsi_omega_skill_report_v1")
    parser.add_argument("--mode", default="full")
    parser.add_argument("--state_dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = verify(Path(args.state_dir).resolve(), mode=str(args.mode))
    print(result)


if __name__ == "__main__":
    main()
