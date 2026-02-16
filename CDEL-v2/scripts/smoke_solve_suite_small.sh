#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"
OUTDIR="$WORKDIR/out"

cd "$ROOT_DIR"

mkdir -p "$WORKDIR"
cdel --root "$WORKDIR" init --budget 1000000
cdel --root "$WORKDIR" sealed keygen --out "$WORKDIR/sealed_keypair.json"

python3 - <<PY
from pathlib import Path
import json
from cdel.config import load_config, write_config

root = Path("$WORKDIR")
cfg = load_config(root)
data = cfg.data
keypair = json.loads((root / "sealed_keypair.json").read_text(encoding="utf-8"))
data["sealed"] = {
    "public_key": keypair["public_key"],
    "key_id": keypair["key_id"],
    "public_keys": [],
    "prev_public_keys": [],
    "alpha_total": "2",
    "alpha_schedule": {"name": "p_series", "exponent": 2, "coefficient": "0.60792710185402662866"},
    "eval_harness_id": "toy-harness-v1",
    "eval_harness_hash": "harness-hash",
    "eval_suite_hash": "suite-hash",
}
write_config(root, data)
PY

PRIVATE_KEY="$(python3 - <<PY
import json
from pathlib import Path
print(json.loads(Path("$WORKDIR/sealed_keypair.json").read_text(encoding="utf-8"))["private_key"])
PY
)"

CDEL_SEALED_PRIVKEY="$PRIVATE_KEY" cdel --root "$WORKDIR" solve-suite \
  --suite trackA \
  --limit 3 \
  --budget-per-task 100000 \
  --max-candidates 2 \
  --episodes 8 \
  --seed-key sealed-seed \
  --outdir "$OUTDIR" >/dev/null

test -f "$OUTDIR/suite_scoreboard.json"
test -f "$OUTDIR/suite_summary.md"

python3 - <<PY
import json
from pathlib import Path

payload = json.loads(Path("$OUTDIR/suite_scoreboard.json").read_text(encoding="utf-8"))
tasks = payload.get("tasks") or []
if not tasks:
    raise SystemExit("no tasks recorded in suite scoreboard")
if not any(row.get("accepted") for row in tasks):
    raise SystemExit("suite solve did not accept any task")
for row in tasks:
    for attempt in row.get("attempts") or []:
        alpha = attempt.get("alpha") or {}
        if alpha and alpha.get("threshold") is None:
            raise SystemExit("missing alpha audit fields in suite scoreboard")
PY

if [[ -n "${CDEL_CI_ARTIFACTS_DIR:-}" ]]; then
  mkdir -p "$CDEL_CI_ARTIFACTS_DIR"
  cp "$OUTDIR/suite_scoreboard.json" "$CDEL_CI_ARTIFACTS_DIR/"
  cp "$OUTDIR/suite_summary.md" "$CDEL_CI_ARTIFACTS_DIR/"
fi

echo "smoke_solve_suite_out=$OUTDIR"
echo "$WORKDIR"
