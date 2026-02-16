import json
import runpy
import sys
from pathlib import Path


def _run_check_claims(runs_root: Path, out_path: Path) -> None:
    argv = ["check_claims.py", "--runs", str(runs_root), "--out", str(out_path)]
    old_argv = sys.argv
    sys.argv = argv
    try:
        runpy.run_path(str(Path("analysis/check_claims.py")), run_name="__main__")
    finally:
        sys.argv = old_argv


def test_claims_skip_semantics(tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    manifest = {
        "suite_name": "runs_partial",
        "claim_complete": False,
        "claims": {},
    }
    (runs_root / "suite_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    out_path = tmp_path / "claims_report.json"
    _run_check_claims(runs_root, out_path)
    report = json.loads(out_path.read_text(encoding="utf-8"))
    statuses = {claim["claim"]: claim.get("status") for claim in report.get("claims", [])}
    assert statuses.get("C3_scan_baseline") == "SKIP"
