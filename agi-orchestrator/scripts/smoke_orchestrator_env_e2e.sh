#!/usr/bin/env bash
set -euo pipefail
# Config materialization delegated to smoke_config.py to preserve sealed.episodes and avoid CDEL config round-trip.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

export PYTHONPATH="$ROOT_DIR"

cdel_cmd() {
  "$PYTHON_BIN" -m cdel.cli "$@"
}

mkdir -p "$WORKDIR/sealed_suites"
HELDOUT_DIR="$(mktemp -d)"
: > "$WORKDIR/config.toml"

"$PYTHON_BIN" - <<PY
import json
from pathlib import Path

dev_path = Path("$WORKDIR") / "sealed_suites" / "env_dev.jsonl"
heldout_path = Path("$HELDOUT_DIR") / "env_heldout.jsonl"

rows = [
    {"episode": 0, "env": "gridworld-v1", "start": {"x": 0, "y": 0}, "goal": {"x": 3, "y": 0}, "max_steps": 8, "walls": []},
    {"episode": 1, "env": "gridworld-v1", "start": {"x": 0, "y": 0}, "goal": {"x": 0, "y": 3}, "max_steps": 8, "walls": []},
    {"episode": 2, "env": "gridworld-v1", "start": {"x": 1, "y": 1}, "goal": {"x": 3, "y": 1}, "max_steps": 8, "walls": []},
    {"episode": 3, "env": "gridworld-v1", "start": {"x": 2, "y": 2}, "goal": {"x": 0, "y": 2}, "max_steps": 8, "walls": []},
]
content = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
dev_path.write_text(content, encoding="utf-8")
heldout_path.write_text(content, encoding="utf-8")
PY

DEV_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$WORKDIR/sealed_suites/env_dev.jsonl")"
HELDOUT_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$HELDOUT_DIR/env_heldout.jsonl")"
mv "$WORKDIR/sealed_suites/env_dev.jsonl" "$WORKDIR/sealed_suites/${DEV_HASH}.jsonl"
mv "$HELDOUT_DIR/env_heldout.jsonl" "$HELDOUT_DIR/${HELDOUT_HASH}.jsonl"

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
from orchestrator.smoke_config import materialize_env_config

root = Path("$WORKDIR")
keypair = json.loads((root / "sealed_keypair.json").read_text(encoding="utf-8"))

materialize_env_config(
    out_path=root / "dev_env_config.toml",
    suite_hash="$DEV_HASH",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=4,
)
materialize_env_config(
    out_path=root / "heldout_env_config.toml",
    suite_hash="$HELDOUT_HASH",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=4,
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
        "new_symbols": ["policy_base", "policy_oracle"],
        "definitions": [
            {
                "name": "policy_base",
                "params": [
                    {"name": "agent_x", "type": {"tag": "int"}},
                    {"name": "agent_y", "type": {"tag": "int"}},
                    {"name": "goal_x", "type": {"tag": "int"}},
                    {"name": "goal_y", "type": {"tag": "int"}},
                ],
                "ret_type": {"tag": "int"},
                "body": {"tag": "int", "value": 0},
                "termination": {"kind": "structural", "decreases_param": None},
            },
            {
                "name": "policy_oracle",
                "params": [
                    {"name": "agent_x", "type": {"tag": "int"}},
                    {"name": "agent_y", "type": {"tag": "int"}},
                    {"name": "goal_x", "type": {"tag": "int"}},
                    {"name": "goal_y", "type": {"tag": "int"}},
                ],
                "ret_type": {"tag": "int"},
                "body": {"tag": "int", "value": 3},
                "termination": {"kind": "structural", "decreases_param": None},
            },
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [{"concept": "gridworld", "symbol": "policy_base"}],
    },
}
(root / "module_base.json").write_text(json.dumps(base, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/heldout_env_config.toml" commit "$WORKDIR/module_base.json"

"$PYTHON_BIN" "$ROOT_DIR/scripts/run_orchestrator.py" \
  --root "$WORKDIR" \
  --domain env-gridworld-v1 \
  --dev-config "$WORKDIR/dev_env_config.toml" \
  --heldout-config "$WORKDIR/heldout_env_config.toml" \
  --heldout-suites-dir "$HELDOUT_DIR" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 1 \
  --max-attempts 1 \
  --runs-dir "$WORKDIR/orchestrator_runs"

echo "$WORKDIR"
