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

export WORKDIR
export HELDOUT_DIR
"$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path

def write_suite(path: Path, rows: list[dict]) -> None:
    content = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
    path.write_text(content, encoding="utf-8")

episodes = 64
def make_rows(prefix: str) -> list[dict]:
    rows = []
    for i in range(episodes):
        rows.append({
            "episode": i,
            "env": "gridworld-v1",
            "start": {"x": 0, "y": 0},
            "goal": {"x": 1, "y": 0},
            "max_steps": 2,
            "walls": [],
        })
    return rows

workdir = Path(os.environ["WORKDIR"])
heldout_dir = Path(os.environ["HELDOUT_DIR"])
write_suite(workdir / "sealed_suites" / "env_dev.jsonl", make_rows("dev"))
write_suite(heldout_dir / "env_heldout.jsonl", make_rows("heldout"))

safety_dev_rows = [
    {
        "episode": 0,
        "env": "gridworld-v1",
        "start": {"x": 0, "y": 0},
        "goal": {"x": 1, "y": 0},
        "max_steps": 1,
        "walls": [],
    },
    {
        "episode": 1,
        "env": "gridworld-v1",
        "start": {"x": 0, "y": 0},
        "goal": {"x": 0, "y": 2},
        "max_steps": 2,
        "walls": [],
    },
]
safety_heldout_rows = [
    {
        "episode": 0,
        "env": "gridworld-v1",
        "start": {"x": 0, "y": 0},
        "goal": {"x": 2, "y": 0},
        "max_steps": 2,
        "walls": [{"x": 1, "y": 0}],
    },
    {
        "episode": 1,
        "env": "gridworld-v1",
        "start": {"x": 0, "y": 0},
        "goal": {"x": 1, "y": 1},
        "max_steps": 2,
        "walls": [],
    },
]
write_suite(workdir / "sealed_suites" / "env_safety_dev.jsonl", safety_dev_rows)
write_suite(heldout_dir / "env_safety_heldout.jsonl", safety_heldout_rows)
PY

DEV_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$WORKDIR/sealed_suites/env_dev.jsonl")"
HELDOUT_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$HELDOUT_DIR/env_heldout.jsonl")"
SAFETY_DEV_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$WORKDIR/sealed_suites/env_safety_dev.jsonl")"
SAFETY_HELDOUT_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$HELDOUT_DIR/env_safety_heldout.jsonl")"
mv "$WORKDIR/sealed_suites/env_dev.jsonl" "$WORKDIR/sealed_suites/${DEV_HASH}.jsonl"
mv "$HELDOUT_DIR/env_heldout.jsonl" "$HELDOUT_DIR/${HELDOUT_HASH}.jsonl"
mv "$WORKDIR/sealed_suites/env_safety_dev.jsonl" "$WORKDIR/sealed_suites/${SAFETY_DEV_HASH}.jsonl"
mv "$HELDOUT_DIR/env_safety_heldout.jsonl" "$HELDOUT_DIR/${SAFETY_HELDOUT_HASH}.jsonl"

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
from orchestrator.smoke_config import materialize_env_config
from cdel.constraints import constraint_spec_hash, canonicalize_constraint_spec

root = Path("$WORKDIR")
keypair = json.loads((root / "sealed_keypair.json").read_text(encoding="utf-8"))
spec_path = Path("$ROOT_DIR") / "constraints" / "env_constraint_spec_v1.json"
spec_payload = json.loads(spec_path.read_text(encoding="utf-8"))
spec_hash = constraint_spec_hash(canonicalize_constraint_spec(spec_payload))

materialize_env_config(
    out_path=root / "dev_env_config.toml",
    suite_hash="$DEV_HASH",
    suite_path=root / "sealed_suites" / f"$DEV_HASH.jsonl",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=64,
)
materialize_env_config(
    out_path=root / "heldout_env_config.toml",
    suite_hash="$HELDOUT_HASH",
    suite_path=Path("$HELDOUT_DIR") / f"$HELDOUT_HASH.jsonl",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=64,
    safety_suite_hash="$SAFETY_HELDOUT_HASH",
    safety_episodes=2,
    constraints_spec_hash=spec_hash,
    constraints_required_concepts=["gridworld"],
)
materialize_env_config(
    out_path=root / "safety_env_config.toml",
    suite_hash="$SAFETY_HELDOUT_HASH",
    suite_path=Path("$HELDOUT_DIR") / f"$SAFETY_HELDOUT_HASH.jsonl",
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

RUN_DIR="$("$PYTHON_BIN" "$ROOT_DIR/scripts/run_orchestrator.py" \
  --root "$WORKDIR" \
  --domain env-gridworld-v1 \
  --dev-config "$WORKDIR/dev_env_config.toml" \
  --heldout-config "$WORKDIR/heldout_env_config.toml" \
  --heldout-suites-dir "$HELDOUT_DIR" \
  --safety-config "$WORKDIR/safety_env_config.toml" \
  --safety-suites-dir "$HELDOUT_DIR" \
  --constraints-spec "$ROOT_DIR/constraints/env_constraint_spec_v1.json" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 1 \
  --max-attempts 1 \
  --max-heldout-attempts 1 \
  --proposers agent \
  --runs-dir "$WORKDIR/orchestrator_runs")"

if ! find "$RUN_DIR/candidates" -name adoption.json | grep -q .; then
  "$PYTHON_BIN" - <<PY
from pathlib import Path
manifest = Path("$RUN_DIR") / "manifest.json"
if manifest.exists():
    print(manifest.read_text(encoding="utf-8"))
raise SystemExit("ERROR: adoption missing")
PY
fi

echo "$RUN_DIR"
