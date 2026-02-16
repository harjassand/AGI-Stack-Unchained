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
    "alpha_total": "1e-4",
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

CDEL_SEALED_PRIVKEY="$PRIVATE_KEY" cdel --root "$WORKDIR" solve \
  --task pred.lt_k.7 \
  --episodes 128 \
  --max-candidates 2 \
  --seed-key sealed-seed > "$WORKDIR/solve_out.json"

mkdir -p "$OUTDIR"
cp "$WORKDIR/solve_out.json" "$OUTDIR/solve_out.json"

python3 - <<PY
import json
from pathlib import Path

payload = json.loads(Path("$WORKDIR/solve_out.json").read_text(encoding="utf-8"))
attempts = payload.get("attempts") or []
if not any(a.get("accepted") for a in attempts):
    raise SystemExit("solve failed to accept a candidate")
alpha = next((a.get("alpha") for a in attempts if a.get("accepted")), None)
if not alpha or alpha.get("threshold") is None or alpha.get("evalue") is None:
    raise SystemExit("missing alpha audit info")
lines = [
    "# Solve Smoke Summary",
    "",
    f"- task_id: {payload.get('task_id')}",
    f"- attempts: {len(attempts)}",
    f"- accepted: {any(a.get('accepted') for a in attempts)}",
]
if alpha:
    lines.append(f"- alpha_i: {alpha.get('alpha_i')}")
    lines.append(f"- threshold: {alpha.get('threshold')}")
    lines.append(f"- evalue: {alpha.get('evalue')}")
Path("$OUTDIR/summary.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
PY

cdel --root "$WORKDIR" resolve --concept pred.lt_k.7 --show-active --show-cert-summary >/dev/null

cdel run-solve-scoreboard \
  --out "$OUTDIR/scoreboard" \
  --tasks 6 \
  --max-candidates 2 \
  --episodes 16 \
  --budget 100000 >/dev/null

if [[ -n "${CDEL_CI_ARTIFACTS_DIR:-}" ]]; then
  mkdir -p "$CDEL_CI_ARTIFACTS_DIR"
  cp -R "$OUTDIR"/. "$CDEL_CI_ARTIFACTS_DIR"/
fi

echo "smoke_solve_out=$OUTDIR"
echo "$WORKDIR"
