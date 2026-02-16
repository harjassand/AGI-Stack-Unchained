#!/usr/bin/env bash
set -euo pipefail
# Budget failure smoke ensures LLM call budgets are enforced.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="$ROOT_DIR"

export ORCH_LLM_BACKEND="mock"
export ORCH_LLM_MOCK_MODE="invalid_then_valid"
export ORCH_LLM_MAX_CALLS="1"
ORCH_LLM_MOCK_RESPONSE="$("$PYTHON_BIN" - <<'PY'
import json

payload = {
    "new_symbols": ["is_even_budget"],
    "definitions": [
        {
            "name": "is_even_budget",
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
        }
    ],
    "declared_deps": [],
    "specs": [],
    "concepts": [{"concept": "algo.is_even", "symbol": "is_even_budget"}],
}
print(json.dumps(payload, sort_keys=True))
PY
)"
export ORCH_LLM_MOCK_RESPONSE

cdel_cmd() {
  "$PYTHON_BIN" -m cdel.cli "$@"
}

mkdir -p "$WORKDIR/sealed_suites"
HELDOUT_DIR="$(mktemp -d)"
: > "$WORKDIR/config.toml"

"$PYTHON_BIN" - <<PY
import json
from pathlib import Path

dev_path = Path("$WORKDIR") / "sealed_suites" / "io_dev.jsonl"
heldout_path = Path("$HELDOUT_DIR") / "io_heldout.jsonl"

def write_rows(path: Path, start: int) -> None:
    rows = []
    for i, n in enumerate(range(start, start + 2)):
        rows.append({
            "episode": i,
            "args": [{"tag": "int", "value": n}],
            "target": {"tag": "bool", "value": (n % 2 == 0)},
        })
    content = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
    path.write_text(content, encoding="utf-8")

write_rows(dev_path, 0)
write_rows(heldout_path, 2)
PY

DEV_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$WORKDIR/sealed_suites/io_dev.jsonl")"
HELDOUT_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$HELDOUT_DIR/io_heldout.jsonl")"
mv "$WORKDIR/sealed_suites/io_dev.jsonl" "$WORKDIR/sealed_suites/${DEV_HASH}.jsonl"
mv "$HELDOUT_DIR/io_heldout.jsonl" "$HELDOUT_DIR/${HELDOUT_HASH}.jsonl"

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" init --budget 1000000
keypair_json="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed keygen --out - || true)"
if [[ -z "$keypair_json" ]]; then
  keypair_json="$("$PYTHON_BIN" - <<'PY'
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
import json

priv, pub = generate_keypair()
print(json.dumps({"private_key": priv, "public_key": pub, "key_id": key_id_from_public_key(pub)}, sort_keys=True))
PY
)"
fi
printf '%s\n' "$keypair_json" > "$WORKDIR/sealed_keypair.json"

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

materialize_io_config(
    out_path=root / "dev_config.toml",
    suite_hash="$DEV_HASH",
    suite_path=root / "sealed_suites" / f"$DEV_HASH.jsonl",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=2,
)
materialize_io_config(
    out_path=root / "heldout_config.toml",
    suite_hash="$HELDOUT_HASH",
    suite_path=Path("$HELDOUT_DIR") / f"$HELDOUT_HASH.jsonl",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=2,
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
                            "args": [
                                {"tag": "var", "name": "n"},
                                {"tag": "int", "value": 2},
                            ],
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

if run_output="$("$PYTHON_BIN" "$ROOT_DIR/scripts/run_orchestrator.py" \
  --root "$WORKDIR" \
  --concept algo.is_even \
  --oracle is_even_oracle \
  --baseline is_even_base \
  --dev-config "$WORKDIR/dev_config.toml" \
  --heldout-config "$WORKDIR/heldout_config.toml" \
  --heldout-suites-dir "$HELDOUT_DIR" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 0 \
  --max-attempts 1 \
  --max-heldout-attempts 0 \
  --proposers llm \
  --runs-dir "$WORKDIR/orchestrator_runs" 2>&1)"; then
  echo "ERROR: expected budget failure but run succeeded"
  exit 1
fi

if ! echo "$run_output" | grep -q "llm call budget exceeded"; then
  echo "ERROR: expected budget error not found"
  exit 1
fi

if find "$WORKDIR/orchestrator_runs" -name adoption.json | grep -q .; then
  echo "ERROR: adoption output should not exist"
  exit 1
fi
