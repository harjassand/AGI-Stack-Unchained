#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"
HELDOUT_HASH="8d42e9e39e6437c2907d789ede94020dbe6fd6f415ad3b03115a8043421f5300"

cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python3
fi

cdel_cmd() {
  "$PYTHON_BIN" -m cdel.cli "$@"
}

HELDOUT_DIR="$(mktemp -d)"
export CDEL_SUITES_DIR="$HELDOUT_DIR"

python3 - <<PY
import json
from pathlib import Path

path = Path("$HELDOUT_DIR") / "${HELDOUT_HASH}.jsonl"
rows = [
    {"episode": 0, "env": "gridworld-v1", "start": {"x": 0, "y": 0}, "goal": {"x": 3, "y": 0}, "max_steps": 8, "walls": []},
    {"episode": 1, "env": "gridworld-v1", "start": {"x": 0, "y": 0}, "goal": {"x": 0, "y": 3}, "max_steps": 8, "walls": []},
    {"episode": 2, "env": "gridworld-v1", "start": {"x": 1, "y": 1}, "goal": {"x": 3, "y": 1}, "max_steps": 8, "walls": []},
    {"episode": 3, "env": "gridworld-v1", "start": {"x": 2, "y": 2}, "goal": {"x": 0, "y": 2}, "max_steps": 8, "walls": []},
]
content = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
path.write_text(content, encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" init --budget 1000000
cdel_cmd --root "$WORKDIR" sealed keygen --out "$WORKDIR/sealed_keypair.json"

python3 - <<PY
from pathlib import Path
import json
from cdel.config import load_config_from_path, write_config_path

root = Path("$WORKDIR")
template = Path("$ROOT_DIR/configs/sealed_env_heldout.toml")
cfg = load_config_from_path(root, template)
data = cfg.data
keypair = json.loads((root / "sealed_keypair.json").read_text(encoding="utf-8"))
sealed = dict(data.get("sealed") or {})
episodes = sealed.get("episodes")
sealed["public_key"] = keypair["public_key"]
sealed["key_id"] = keypair["key_id"]
sealed.setdefault("public_keys", [])
sealed.setdefault("prev_public_keys", [])
data["sealed"] = sealed
out_path = root / "sealed_env_heldout.toml"
write_config_path(out_path, data)
if isinstance(episodes, int):
    lines = out_path.read_text(encoding="utf-8").splitlines()
    out_lines = []
    inserted = False
    for line in lines:
        out_lines.append(line)
        if line.startswith("eval_suite_hash"):
            out_lines.append(f"episodes = {episodes}")
            inserted = True
    if not inserted:
        raise RuntimeError("failed to inject episodes into config")
    out_path.write_text("\n".join(out_lines).strip() + "\n", encoding="utf-8")
PY

python3 - <<PY
from pathlib import Path
import json

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
        "concepts": [],
    },
}
(root / "module_base.json").write_text(json.dumps(base, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/sealed_env_heldout.toml" commit "$WORKDIR/module_base.json"

python3 - <<PY
from pathlib import Path
import json

root = Path("$WORKDIR")
policy = {
    "new_symbols": ["policy_candidate"],
    "definitions": [
        {
            "name": "policy_candidate",
            "params": [
                {"name": "agent_x", "type": {"tag": "int"}},
                {"name": "agent_y", "type": {"tag": "int"}},
                {"name": "goal_x", "type": {"tag": "int"}},
                {"name": "goal_y", "type": {"tag": "int"}},
            ],
            "ret_type": {"tag": "int"},
            "body": {
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
            },
            "termination": {"kind": "structural", "decreases_param": None},
        }
    ],
    "declared_deps": ["policy_base", "policy_oracle"],
    "specs": [],
    "concepts": [{"concept": "gridworld", "symbol": "policy_candidate"}],
}
(root / "candidate_defs.json").write_text(json.dumps(policy, sort_keys=True) + "\n", encoding="utf-8")

spec = {
    "kind": "stat_cert",
    "concept": "gridworld",
    "metric": "accuracy",
    "null": "no_improvement",
    "baseline_symbol": "policy_base",
    "candidate_symbol": "policy_candidate",
    "eval": {"episodes": 4, "max_steps": 16, "paired_seeds": True, "oracle_symbol": "policy_oracle"},
    "risk": {"evalue_threshold": "1e-6"},
}
(root / "stat_cert_request.json").write_text(json.dumps(spec, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/sealed_env_heldout.toml" sealed worker \
  --request "$WORKDIR/stat_cert_request.json" \
  --out "$WORKDIR/stat_cert_signed.json" \
  --private-key "$(python3 - <<PY
import json
from pathlib import Path
print(json.loads(Path("$WORKDIR/sealed_keypair.json").read_text(encoding="utf-8"))["private_key"])
PY
)" \
  --seed-key "sealed-seed" \
  --candidate-module "$WORKDIR/candidate_defs.json"

python3 - <<PY
from pathlib import Path
import json

root = Path("$WORKDIR")
spec = json.loads((root / "stat_cert_signed.json").read_text(encoding="utf-8"))
candidate = json.loads((root / "candidate_defs.json").read_text(encoding="utf-8"))
module = {
    "schema_version": 1,
    "dsl_version": 1,
    "parent": (root / "ledger" / "head").read_text(encoding="utf-8").strip(),
    "payload": {
        **candidate,
        "specs": [spec],
    },
}
(root / "module_candidate.json").write_text(json.dumps(module, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/sealed_env_heldout.toml" commit "$WORKDIR/module_candidate.json"

python3 - <<PY
from pathlib import Path
import json

root = Path("$WORKDIR")
spec = json.loads((root / "stat_cert_signed.json").read_text(encoding="utf-8"))
adoption = {
    "schema_version": 1,
    "parent": (root / "adoption" / "head").read_text(encoding="utf-8").strip(),
    "payload": {
        "concept": "gridworld",
        "chosen_symbol": "policy_candidate",
        "baseline_symbol": None,
        "certificate": spec,
        "constraints": {},
    },
}
(root / "adoption.json").write_text(json.dumps(adoption, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/sealed_env_heldout.toml" adopt "$WORKDIR/adoption.json"
cdel_cmd --root "$WORKDIR" --config "$WORKDIR/sealed_env_heldout.toml" resolve --concept gridworld >/dev/null

echo "$WORKDIR"
