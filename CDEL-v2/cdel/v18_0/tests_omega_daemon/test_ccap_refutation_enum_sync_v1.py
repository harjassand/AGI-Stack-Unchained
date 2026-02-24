from __future__ import annotations

import json
from pathlib import Path


_NEW_CODES = {
    "EK_EXT_LEDGER_PIN_MISMATCH",
    "EK_SUITE_RUNNER_PIN_MISMATCH",
    "EK_SUITE_LIST_MISMATCH",
    "EK_EXTENSION_SUITE_FAILED",
    "EK_ANCHOR_SUITE_FAILED",
}


def _enum_codes(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return set(payload["properties"]["refutation_code"]["enum"])


def test_ccap_refutation_enum_contains_phase1_kernel_composition_codes_in_both_schema_copies() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    cdel_schema = repo_root / "CDEL-v2" / "Genesis" / "schema" / "v18_0" / "ccap_refutation_cert_v1.jsonschema"
    genesis_schema = repo_root / "Genesis" / "schema" / "v18_0" / "ccap_refutation_cert_v1.jsonschema"

    cdel_codes = _enum_codes(cdel_schema)
    genesis_codes = _enum_codes(genesis_schema)

    assert _NEW_CODES.issubset(cdel_codes)
    assert _NEW_CODES.issubset(genesis_codes)
