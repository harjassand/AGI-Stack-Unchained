#!/usr/bin/env bash
set -euo pipefail
# Replay backend smoke to catch prompt drift deterministically.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="$ROOT_DIR"

export ORCH_LLM_BACKEND="replay"
export ORCH_LLM_REPLAY_PATH="$ROOT_DIR/tests/fixtures/llm_replays/io_algorithms_v1_replay.jsonl"
export ORCH_LLM_MAX_CALLS="3"

cdel_cmd() {
  "$PYTHON_BIN" -m cdel.cli "$@"
}

mkdir -p "$WORKDIR/sealed_suites"
: > "$WORKDIR/config.toml"

"$PYTHON_BIN" - <<PY
import json
from pathlib import Path
from blake3 import blake3

root = Path("$WORKDIR")
rows = [
    {"episode": 0, "args": [{"tag": "int", "value": 0}], "target": {"tag": "bool", "value": True}},
]
content = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
content_bytes = content.encode("utf-8")
content_hash = blake3(content_bytes).hexdigest()
path = root / "sealed_suites" / f"{content_hash}.jsonl"
path.write_bytes(content_bytes)
print(content_hash)
PY

DEV_HASH=$(ls "$WORKDIR/sealed_suites" | sed -n '1p' | sed 's/\.jsonl$//')

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" init --budget 1000000
keypair_json="$($PYTHON_BIN -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed keygen --out - || true)"
if [[ -z "$keypair_json" ]]; then
  keypair_json="$($PYTHON_BIN - <<'PY'
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
import json

priv, pub = generate_keypair()
print(json.dumps({"private_key": priv, "public_key": pub, "key_id": key_id_from_public_key(pub)}, sort_keys=True))
PY
)"
fi
printf '%s\n' "$keypair_json" > "$WORKDIR/sealed_keypair.json"

export CDEL_SEALED_PRIVKEY
CDEL_SEALED_PRIVKEY="$($PYTHON_BIN - <<PY
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
    episodes=1,
)
materialize_io_config(
    out_path=root / "heldout_config.toml",
    suite_hash="$DEV_HASH",
    suite_path=root / "sealed_suites" / f"$DEV_HASH.jsonl",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=1,
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

RUN_DIR="$($PYTHON_BIN "$ROOT_DIR/scripts/run_orchestrator.py" \
  --root "$WORKDIR" \
  --concept algo.is_even \
  --oracle is_even_oracle \
  --baseline is_even_base \
  --dev-config "$WORKDIR/dev_config.toml" \
  --heldout-config "$WORKDIR/heldout_config.toml" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 0 \
  --max-attempts 1 \
  --max-heldout-attempts 0 \
  --proposers llm \
  --runs-dir "$WORKDIR/orchestrator_runs")"

"$PYTHON_BIN" - <<PY
from pathlib import Path

cache_dir = Path("$RUN_DIR") / "llm_cache"
if not cache_dir.exists():
    raise SystemExit("ERROR: llm_cache directory missing")
PY

echo "$RUN_DIR"
