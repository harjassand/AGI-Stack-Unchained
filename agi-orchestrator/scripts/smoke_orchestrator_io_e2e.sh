#!/usr/bin/env bash
set -euo pipefail
# Config materialization delegated to smoke_config.py to preserve sealed.episodes and avoid CDEL config round-trip.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"

export PYTHONPATH="$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

cdel_cmd() {
  "$PYTHON_BIN" -m cdel.cli "$@"
}

mkdir -p "$WORKDIR/sealed_suites"
HELDOUT_DIR="$(mktemp -d)"
: > "$WORKDIR/config.toml"
# Use 128 episodes to stabilize heldout e-value over the default alpha schedule.
"$PYTHON_BIN" - <<PY
import json
from pathlib import Path

dev_path = Path("$WORKDIR") / "sealed_suites" / "io_dev.jsonl"
heldout_path = Path("$HELDOUT_DIR") / "io_heldout.jsonl"

def write_rows(path: Path, start: int) -> None:
    rows = []
    for i, n in enumerate(range(start, start + 128)):
        rows.append({
            "episode": i,
            "args": [{"tag": "int", "value": n}],
            "target": {"tag": "bool", "value": (n % 2 == 0)},
        })
    content = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
    path.write_text(content, encoding="utf-8")

write_rows(dev_path, 0)
write_rows(heldout_path, 128)
PY

DEV_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$WORKDIR/sealed_suites/io_dev.jsonl")"
HELDOUT_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$HELDOUT_DIR/io_heldout.jsonl")"
mv "$WORKDIR/sealed_suites/io_dev.jsonl" "$WORKDIR/sealed_suites/${DEV_HASH}.jsonl"
mv "$HELDOUT_DIR/io_heldout.jsonl" "$HELDOUT_DIR/${HELDOUT_HASH}.jsonl"

mkdir -p "$WORKDIR"
cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" init --budget 1000000
cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed keygen --out "$WORKDIR/sealed_keypair.json"

export CDEL_SEALED_PRIVKEY
CDEL_SEALED_PRIVKEY="$("$PYTHON_BIN" - <<PY
import json
from pathlib import Path
print(json.loads(Path("$WORKDIR/sealed_keypair.json").read_text(encoding="utf-8"))["private_key"])
PY
)"

"$PYTHON_BIN" - <<PY
import json
from pathlib import Path
from orchestrator.smoke_config import materialize_io_config

root = Path("$WORKDIR")
keypair = json.loads((root / "sealed_keypair.json").read_text(encoding="utf-8"))
dev_suite = root / "sealed_suites" / "${DEV_HASH}.jsonl"
heldout_suite = Path("$HELDOUT_DIR") / "${HELDOUT_HASH}.jsonl"

materialize_io_config(
    out_path=root / "dev_config.toml",
    suite_hash="$DEV_HASH",
    suite_path=dev_suite,
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=128,
)
materialize_io_config(
    out_path=root / "heldout_config.toml",
    suite_hash="$HELDOUT_HASH",
    suite_path=heldout_suite,
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=128,
)
PY

"$PYTHON_BIN" - <<PY
import json
from pathlib import Path

root = Path("$WORKDIR")
base = {
    "schema_version": 1,
    "dsl_version": 1,
    "parent": "GENESIS",
    "payload": {
        "new_symbols": ["is_even_base", "is_even_oracle"],
        "definitions": [
            {
                "name": "is_even_base",
                "params": [{"name": "n", "type": {"tag": "int"}}],
                "ret_type": {"tag": "bool"},
                "body": {"tag": "bool", "value": False},
                "termination": {"kind": "structural", "decreases_param": None},
            },
            {
                "name": "is_even_oracle",
                "params": [{"name": "n", "type": {"tag": "int"}}],
                "ret_type": {"tag": "bool"},
                "body": {
                    "tag": "prim",
                    "op": "eq_int",
                    "args": [
                        {
                            "tag": "prim",
                            "op": "mod",
                            "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": 2}],
                        },
                        {"tag": "int", "value": 0},
                    ],
                },
                "termination": {"kind": "structural", "decreases_param": None},
            },
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [],
    },
}
(root / "module_base.json").write_text(json.dumps(base, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/heldout_config.toml" commit "$WORKDIR/module_base.json"

RUN_DIR="$("$PYTHON_BIN" "$ROOT_DIR/scripts/run_orchestrator.py" \
  --root "$WORKDIR" \
  --domain io-algorithms-v1 \
  --dev-config "$WORKDIR/dev_config.toml" \
  --heldout-config "$WORKDIR/heldout_config.toml" \
  --heldout-suites-dir "$HELDOUT_DIR" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 2 \
  --max-attempts 1 \
  --runs-dir "$WORKDIR/orchestrator_runs")"

if ! find "$RUN_DIR/candidates" -name adoption.json | grep -q .; then
  "$PYTHON_BIN" - <<PY
import json
from pathlib import Path

manifest = Path("$RUN_DIR") / "manifest.json"
if not manifest.exists():
    raise SystemExit("ERROR: adoption missing and manifest not found")
data = json.loads(manifest.read_text(encoding="utf-8"))
reason = data.get("reason", "unknown")
raise SystemExit(f"ERROR: expected adoption output (reason={reason})")
PY
  exit 1
fi

echo "$RUN_DIR"
