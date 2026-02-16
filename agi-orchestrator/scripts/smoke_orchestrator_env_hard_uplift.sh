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


def hard_rows(offset: int, multiplier: int) -> list[dict]:
    rows = []
    for i in range(24):
        rows.append(
            {
                "episode": i,
                "env": "gridworld-v1",
                "start": {"x": 0, "y": (i + offset) % 5},
                "goal": {"x": 4, "y": (i * multiplier + offset) % 5},
                "max_steps": 10,
                "walls": [],
            }
        )
    return rows


workdir = Path(os.environ["WORKDIR"])
heldout_dir = Path(os.environ["HELDOUT_DIR"])
write_suite(workdir / "sealed_suites" / "env_hard_dev.jsonl", hard_rows(0, 3))
write_suite(heldout_dir / "env_hard_heldout.jsonl", hard_rows(1, 4))

safety_rows = [
    {
        "episode": 0,
        "env": "gridworld-v1",
        "start": {"x": 0, "y": 0},
        "goal": {"x": 1, "y": 0},
        "max_steps": 2,
        "walls": [],
    },
    {
        "episode": 1,
        "env": "gridworld-v1",
        "start": {"x": 0, "y": 0},
        "goal": {"x": 0, "y": 1},
        "max_steps": 1,
        "walls": [],
    },
]
write_suite(workdir / "sealed_suites" / "env_hard_safety_dev.jsonl", safety_rows)
write_suite(heldout_dir / "env_hard_safety_heldout.jsonl", safety_rows)
PY

DEV_HASH="$($PYTHON_BIN -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$WORKDIR/sealed_suites/env_hard_dev.jsonl")"
HELDOUT_HASH="$($PYTHON_BIN -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$HELDOUT_DIR/env_hard_heldout.jsonl")"
SAFETY_DEV_HASH="$($PYTHON_BIN -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$WORKDIR/sealed_suites/env_hard_safety_dev.jsonl")"
SAFETY_HELDOUT_HASH="$($PYTHON_BIN -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$HELDOUT_DIR/env_hard_safety_heldout.jsonl")"

mv "$WORKDIR/sealed_suites/env_hard_dev.jsonl" "$WORKDIR/sealed_suites/${DEV_HASH}.jsonl"
mv "$HELDOUT_DIR/env_hard_heldout.jsonl" "$HELDOUT_DIR/${HELDOUT_HASH}.jsonl"
mv "$WORKDIR/sealed_suites/env_hard_safety_dev.jsonl" "$WORKDIR/sealed_suites/${SAFETY_DEV_HASH}.jsonl"
mv "$HELDOUT_DIR/env_hard_safety_heldout.jsonl" "$HELDOUT_DIR/${SAFETY_HELDOUT_HASH}.jsonl"

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" init --budget 1000000
cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed keygen --out "$WORKDIR/sealed_keypair.json"

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
from orchestrator.smoke_config import materialize_env_config
from cdel.constraints import constraint_spec_hash, canonicalize_constraint_spec

root = Path("$WORKDIR")
keypair = json.loads((root / "sealed_keypair.json").read_text(encoding="utf-8"))
spec_path = Path("$ROOT_DIR") / "constraints" / "env_constraint_spec_v1.json"
spec_payload = json.loads(spec_path.read_text(encoding="utf-8"))
spec_hash = constraint_spec_hash(canonicalize_constraint_spec(spec_payload))

materialize_env_config(
    out_path=root / "env_hard_dev.toml",
    suite_hash="$DEV_HASH",
    suite_path=root / "sealed_suites" / f"$DEV_HASH.jsonl",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=24,
)
materialize_env_config(
    out_path=root / "env_hard_heldout.toml",
    suite_hash="$HELDOUT_HASH",
    suite_path=Path("$HELDOUT_DIR") / f"$HELDOUT_HASH.jsonl",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=24,
    safety_suite_hash="$SAFETY_HELDOUT_HASH",
    safety_episodes=2,
    constraints_spec_hash=spec_hash,
    constraints_required_concepts=["gridworld"],
)
materialize_env_config(
    out_path=root / "env_hard_safety.toml",
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

def greedy_body():
    return {
        "tag": "if",
        "cond": {
            "tag": "prim",
            "op": "lt_int",
            "args": [
                {"tag": "var", "name": "agent_x"},
                {"tag": "var", "name": "goal_x"},
            ],
        },
        "then": {"tag": "int", "value": 3},
        "else": {
            "tag": "if",
            "cond": {
                "tag": "prim",
                "op": "lt_int",
                "args": [
                    {"tag": "var", "name": "goal_x"},
                    {"tag": "var", "name": "agent_x"},
                ],
            },
            "then": {"tag": "int", "value": 2},
            "else": {
                "tag": "if",
                "cond": {
                    "tag": "prim",
                    "op": "lt_int",
                    "args": [
                        {"tag": "var", "name": "agent_y"},
                        {"tag": "var", "name": "goal_y"},
                    ],
                },
                "then": {"tag": "int", "value": 0},
                "else": {
                    "tag": "if",
                    "cond": {
                        "tag": "prim",
                        "op": "lt_int",
                        "args": [
                            {"tag": "var", "name": "goal_y"},
                            {"tag": "var", "name": "agent_y"},
                        ],
                    },
                    "then": {"tag": "int", "value": 1},
                    "else": {"tag": "int", "value": 0},
                },
            },
        },
    }

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
                "body": greedy_body(),
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

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/env_hard_heldout.toml" commit "$WORKDIR/module_base.json"

"$PYTHON_BIN" - <<PY
import json
from pathlib import Path
from orchestrator.plan_skill import PlanStep, build_plan_skill

root = Path("$WORKDIR")
plan_dir = root / "plan_skills"
plan_dir.mkdir(parents=True, exist_ok=True)
plan = build_plan_skill(
    task_id="gridworld",
    steps=[PlanStep(step_idx=0, kind="skill", name="policy_oracle", args={"inputs": {}})],
    dependencies=["policy_oracle"],
    constraints={"domain": "env", "concept": "gridworld", "max_steps": 10},
    example_traces=[],
)
plan_path = plan_dir / f"{plan['plan_id']}.json"
plan_path.write_text(json.dumps(plan, sort_keys=True) + "\n", encoding="utf-8")
PY

RUN_DIR="$($PYTHON_BIN "$ROOT_DIR/scripts/run_orchestrator.py" \
  --root "$WORKDIR" \
  --domain env-gridworld-v1 \
  --dev-config "$WORKDIR/env_hard_dev.toml" \
  --heldout-config "$WORKDIR/env_hard_heldout.toml" \
  --heldout-suites-dir "$HELDOUT_DIR" \
  --safety-config "$WORKDIR/env_hard_safety.toml" \
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
