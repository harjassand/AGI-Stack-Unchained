#!/usr/bin/env bash
set -euo pipefail

REPORT="HARDFIX_REPORT.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --report|--out)
      REPORT="$2"
      shift 2
      ;;
    -h|--help)
      echo "usage: $0 [--report PATH]" >&2
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

python3 - <<'PY'
import json
from pathlib import Path

report_path = Path("""${REPORT}""")

required_docs = [
    "docs/side_channel_audit_checklist.md",
    "docs/dp_accountant_validation_plan.md",
    "docs/alpha_ledger_correctness_proof_sketch.md",
    "docs/red_team_plan.md",
]

doc_status = {}
for doc in required_docs:
    doc_status[doc] = Path(doc).exists()

status = "PASS" if all(doc_status.values()) else "FAIL"

payload = {
    "status": status,
    "checks": {
        "docs_present": doc_status,
    },
}

report_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
PY

if [[ ! -f "$REPORT" ]]; then
  echo "HARDFIX report not written" >&2
  exit 2
fi
