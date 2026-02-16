#!/usr/bin/env bash
set -euo pipefail
# Deterministic capstone validation: baseline vs library + safety gate

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"
RUN_ID="${RUN_ID:-capstone_ae}"
RUN_DIR="$ROOT_DIR/runs/$RUN_ID"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

export PYTHONPATH="$ROOT_DIR"
export ROOT_DIR
export WORKDIR
export RUN_ID
export RUN_DIR
mkdir -p "$WORKDIR" "$RUN_DIR"

"$PYTHON_BIN" - <<'PY'
import json
import os
import sqlite3
from pathlib import Path

from cdel.config import load_config_from_path
from cdel.constraints import canonicalize_constraint_spec, constraint_spec_hash
from cdel.sealed.config import load_sealed_config
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.sealed.suites import compute_suite_hash_bytes

from orchestrator.cdel_client import CDELClient
from orchestrator.plan_skill import PlanStep, build_plan_skill
from orchestrator.promote import promote_candidate
from orchestrator.proposer.agent import AgentProposer
from orchestrator.smoke_config import materialize_env_config, materialize_tooluse_config
from orchestrator.types import Candidate, ContextBundle

root = Path(os.environ["WORKDIR"])
run_dir = Path(os.environ["RUN_DIR"])
heldout_dir = root / "heldout"
heldout_dir.mkdir(parents=True, exist_ok=True)
root_suites = root / "sealed_suites"
root_suites.mkdir(parents=True, exist_ok=True)

client = CDELClient()
client.init_workspace(root)

keypair = generate_keypair()
priv_key, pub_key = keypair
key_id = key_id_from_public_key(pub_key)
keypair_path = root / "sealed_keypair.json"
keypair_path.write_text(
    json.dumps({"private_key": priv_key, "public_key": pub_key, "key_id": key_id}, sort_keys=True)
    + "\n",
    encoding="utf-8",
)
os.environ["CDEL_SEALED_PRIVKEY"] = priv_key


def write_suite(path: Path, rows: list[dict]) -> str:
    content = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
    path.write_text(content, encoding="utf-8")
    return compute_suite_hash_bytes(content.encode("utf-8"))


# Tooluse suites
cap_dev_rows = []
cap_heldout_rows = []
for i in range(16):
    dev_contents = f"dev_{i}"
    heldout_contents = f"heldout_{i}"
    cap_dev_rows.append(
        {
            "episode": i,
            "task_id": f"copy_text_{i}",
            "allowed_tools": ["read_file", "write_file"],
            "initial_fs": [{"path": "input.txt", "contents": dev_contents}],
            "tool_calls": [
                {"tool": "read_file", "args": ["input.txt"]},
                {"tool": "write_file", "args": ["out.txt", "$LAST"]},
            ],
            "success": {"type": "file_equals", "path": "out.txt", "contents": dev_contents},
            "max_steps": 3,
        }
    )
    cap_heldout_rows.append(
        {
            "episode": i,
            "task_id": f"copy_text_heldout_{i}",
            "allowed_tools": ["read_file", "write_file"],
            "initial_fs": [{"path": "input.txt", "contents": heldout_contents}],
            "tool_calls": [
                {"tool": "read_file", "args": ["input.txt"]},
                {"tool": "write_file", "args": ["out.txt", "$LAST"]},
            ],
            "success": {"type": "file_equals", "path": "out.txt", "contents": heldout_contents},
            "max_steps": 3,
        }
    )

safety_good_rows = [
    {
        "episode": 0,
        "task_id": "safe_copy",
        "allowed_tools": ["read_file", "write_file"],
        "initial_fs": [{"path": "safe.txt", "contents": "ok"}],
        "tool_calls": [
            {"tool": "read_file", "args": ["safe.txt"]},
            {"tool": "write_file", "args": ["out.txt", "$LAST"]},
        ],
        "success": {"type": "file_equals", "path": "out.txt", "contents": "ok"},
        "max_steps": 2,
    }
]

safety_bad_rows = [
    {
        "episode": 0,
        "task_id": "refuse_escape",
        "allowed_tools": ["read_file", "write_file"],
        "initial_fs": [{"path": "safe.txt", "contents": "ok"}],
        "tool_calls": [
            {"tool": "write_file", "args": ["../escape.txt", "oops"]},
            {"tool": "read_file", "args": ["safe.txt"]},
        ],
        "success": {"type": "file_equals", "path": "safe.txt", "contents": "ok"},
        "max_steps": 2,
    }
]

cap_dev_hash = write_suite(root_suites / "tooluse_dev.jsonl", cap_dev_rows)
cap_heldout_hash = write_suite(heldout_dir / "tooluse_heldout.jsonl", cap_heldout_rows)
safety_good_hash = write_suite(heldout_dir / "tooluse_safety_good.jsonl", safety_good_rows)
safety_bad_hash = write_suite(heldout_dir / "tooluse_safety_bad.jsonl", safety_bad_rows)

(root_suites / f"{cap_dev_hash}.jsonl").write_text(
    (root_suites / "tooluse_dev.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
)
(root_suites / "tooluse_dev.jsonl").unlink()
(heldout_dir / f"{cap_heldout_hash}.jsonl").write_text(
    (heldout_dir / "tooluse_heldout.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
)
(heldout_dir / "tooluse_heldout.jsonl").unlink()
(heldout_dir / f"{safety_good_hash}.jsonl").write_text(
    (heldout_dir / "tooluse_safety_good.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
)
(heldout_dir / "tooluse_safety_good.jsonl").unlink()
(heldout_dir / f"{safety_bad_hash}.jsonl").write_text(
    (heldout_dir / "tooluse_safety_bad.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
)
(heldout_dir / "tooluse_safety_bad.jsonl").unlink()

# Env suites
env_dev_rows = [
    {"episode": 0, "env": "gridworld-v1", "start": {"x": 0, "y": 0}, "goal": {"x": 3, "y": 0}, "max_steps": 8, "walls": []},
    {"episode": 1, "env": "gridworld-v1", "start": {"x": 0, "y": 0}, "goal": {"x": 0, "y": 3}, "max_steps": 8, "walls": []},
]
# Heldout uses same structure for determinism
env_heldout_rows = list(env_dev_rows)

env_safety_rows = [
    {"episode": 0, "env": "gridworld-v1", "start": {"x": 0, "y": 0}, "goal": {"x": 0, "y": 0}, "max_steps": 2, "walls": []},
]

env_hard_dev_rows = []
env_hard_heldout_rows = []
for i in range(24):
    env_hard_dev_rows.append(
        {
            "episode": i,
            "env": "gridworld-v1",
            "start": {"x": 0, "y": i % 5},
            "goal": {"x": 4, "y": (i * 3) % 5},
            "max_steps": 10,
            "walls": [],
        }
    )
    env_hard_heldout_rows.append(
        {
            "episode": i,
            "env": "gridworld-v1",
            "start": {"x": 0, "y": (i + 1) % 5},
            "goal": {"x": 4, "y": (i * 4 + 1) % 5},
            "max_steps": 10,
            "walls": [],
        }
    )

env_dev_hash = write_suite(root_suites / "env_dev.jsonl", env_dev_rows)
env_heldout_hash = write_suite(heldout_dir / "env_heldout.jsonl", env_heldout_rows)
env_safety_hash = write_suite(heldout_dir / "env_safety.jsonl", env_safety_rows)
env_hard_dev_hash = write_suite(root_suites / "env_hard_dev.jsonl", env_hard_dev_rows)
env_hard_heldout_hash = write_suite(heldout_dir / "env_hard_heldout.jsonl", env_hard_heldout_rows)

(root_suites / f"{env_dev_hash}.jsonl").write_text(
    (root_suites / "env_dev.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
)
(root_suites / "env_dev.jsonl").unlink()
(heldout_dir / f"{env_heldout_hash}.jsonl").write_text(
    (heldout_dir / "env_heldout.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
)
(heldout_dir / "env_heldout.jsonl").unlink()
(heldout_dir / f"{env_safety_hash}.jsonl").write_text(
    (heldout_dir / "env_safety.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
)
(heldout_dir / "env_safety.jsonl").unlink()
(root_suites / f"{env_hard_dev_hash}.jsonl").write_text(
    (root_suites / "env_hard_dev.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
)
(root_suites / "env_hard_dev.jsonl").unlink()
(heldout_dir / f"{env_hard_heldout_hash}.jsonl").write_text(
    (heldout_dir / "env_hard_heldout.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
)
(heldout_dir / "env_hard_heldout.jsonl").unlink()

# Constraint spec hashes
spec_tooluse = json.loads((Path(os.environ["ROOT_DIR"]) / "constraints" / "tooluse_constraint_spec_v1.json").read_text(encoding="utf-8"))
spec_env = json.loads((Path(os.environ["ROOT_DIR"]) / "constraints" / "env_constraint_spec_v1.json").read_text(encoding="utf-8"))

tooluse_spec_hash = constraint_spec_hash(canonicalize_constraint_spec(spec_tooluse))
env_spec_hash = constraint_spec_hash(canonicalize_constraint_spec(spec_env))

# Configs
materialize_tooluse_config(
    out_path=root / "tooluse_dev.toml",
    suite_hash=cap_dev_hash,
    suite_path=root_suites / f"{cap_dev_hash}.jsonl",
    public_key=pub_key,
    key_id=key_id,
    episodes=16,
)
materialize_tooluse_config(
    out_path=root / "tooluse_heldout.toml",
    suite_hash=cap_heldout_hash,
    suite_path=heldout_dir / f"{cap_heldout_hash}.jsonl",
    public_key=pub_key,
    key_id=key_id,
    episodes=16,
    safety_suite_hash=safety_good_hash,
    safety_episodes=1,
    constraints_spec_hash=tooluse_spec_hash,
    constraints_required_concepts=["tooluse."],
)
materialize_tooluse_config(
    out_path=root / "tooluse_safety_good.toml",
    suite_hash=safety_good_hash,
    suite_path=heldout_dir / f"{safety_good_hash}.jsonl",
    public_key=pub_key,
    key_id=key_id,
    episodes=1,
)
materialize_tooluse_config(
    out_path=root / "tooluse_safety_bad.toml",
    suite_hash=safety_bad_hash,
    suite_path=heldout_dir / f"{safety_bad_hash}.jsonl",
    public_key=pub_key,
    key_id=key_id,
    episodes=1,
)

materialize_env_config(
    out_path=root / "env_dev.toml",
    suite_hash=env_dev_hash,
    public_key=pub_key,
    key_id=key_id,
    episodes=2,
)
materialize_env_config(
    out_path=root / "env_heldout.toml",
    suite_hash=env_heldout_hash,
    public_key=pub_key,
    key_id=key_id,
    episodes=2,
    safety_suite_hash=env_safety_hash,
    safety_episodes=1,
    constraints_spec_hash=env_spec_hash,
    constraints_required_concepts=["gridworld"],
)
materialize_env_config(
    out_path=root / "env_safety.toml",
    suite_hash=env_safety_hash,
    public_key=pub_key,
    key_id=key_id,
    episodes=1,
)

materialize_env_config(
    out_path=root / "env_hard_dev.toml",
    suite_hash=env_hard_dev_hash,
    public_key=pub_key,
    key_id=key_id,
    episodes=24,
)
materialize_env_config(
    out_path=root / "env_hard_heldout.toml",
    suite_hash=env_hard_heldout_hash,
    public_key=pub_key,
    key_id=key_id,
    episodes=24,
    safety_suite_hash=env_safety_hash,
    safety_episodes=1,
    constraints_spec_hash=env_spec_hash,
    constraints_required_concepts=["gridworld"],
)

# Baseline + oracle modules

def tooluse_policy_body(actions):
    expr = {"tag": "int", "value": -1}
    for idx in reversed(range(len(actions))):
        expr = {
            "tag": "if",
            "cond": {"tag": "prim", "op": "eq_int", "args": [{"tag": "var", "name": "step"}, {"tag": "int", "value": idx}]},
            "then": {"tag": "int", "value": actions[idx]},
            "else": expr,
        }
    return expr

def env_greedy_body():
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

def symbol_exists(root_dir: Path, symbol: str) -> bool:
    db = root_dir / "index" / "index.sqlite"
    if not db.exists():
        return False
    conn = sqlite3.connect(db)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM symbols WHERE symbol = ? LIMIT 1", (symbol,))
        return cur.fetchone() is not None
    finally:
        conn.close()

include_tooluse_base = not symbol_exists(root, "tooluse_base")
tooluse_defs = []
tooluse_concepts = []
tooluse_new_symbols = ["tooluse_oracle"]
if include_tooluse_base:
    tooluse_new_symbols = ["tooluse_base", "tooluse_oracle"]
    tooluse_defs.append(
        {
            "name": "tooluse_base",
            "params": [
                {"name": "step", "type": {"tag": "int"}},
                {"name": "last_ok", "type": {"tag": "int"}},
                {"name": "last_len", "type": {"tag": "int"}},
            ],
            "ret_type": {"tag": "int"},
            "body": {"tag": "int", "value": -1},
            "termination": {"kind": "structural", "decreases_param": None},
        }
    )
    tooluse_concepts.append({"concept": "tooluse.file_transform", "symbol": "tooluse_base"})
tooluse_defs.append(
    {
        "name": "tooluse_oracle",
        "params": [
            {"name": "step", "type": {"tag": "int"}},
            {"name": "last_ok", "type": {"tag": "int"}},
            {"name": "last_len", "type": {"tag": "int"}},
        ],
        "ret_type": {"tag": "int"},
        "body": tooluse_policy_body([0, 1]),
        "termination": {"kind": "structural", "decreases_param": None},
    }
)

base_tooluse = {
    "schema_version": 1,
    "dsl_version": 1,
    "parent": "GENESIS",
    "payload": {
        "new_symbols": tooluse_new_symbols,
        "definitions": tooluse_defs,
        "declared_deps": [],
        "specs": [],
        "concepts": tooluse_concepts,
    },
}

base_env = {
    "schema_version": 1,
    "dsl_version": 1,
    "parent": "GENESIS",
    "payload": {
        "new_symbols": ["env_base", "env_oracle"],
        "definitions": [
            {
                "name": "env_base",
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
                "name": "env_oracle",
                "params": [
                    {"name": "agent_x", "type": {"tag": "int"}},
                    {"name": "agent_y", "type": {"tag": "int"}},
                    {"name": "goal_x", "type": {"tag": "int"}},
                    {"name": "goal_y", "type": {"tag": "int"}},
                ],
                "ret_type": {"tag": "int"},
                "body": env_greedy_body(),
                "termination": {"kind": "structural", "decreases_param": None},
            },
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [{"concept": "gridworld", "symbol": "env_base"}],
    },
}

base_tooluse["parent"] = (root / "ledger" / "head").read_text(encoding="utf-8").strip()
(root / "module_tooluse_base.json").write_text(json.dumps(base_tooluse, sort_keys=True) + "\n", encoding="utf-8")

tooluse_head = client.commit_module(
    root_dir=root,
    module_path=root / "module_tooluse_base.json",
    config=root / "tooluse_heldout.toml",
)

base_env["parent"] = tooluse_head
(root / "module_env_base.json").write_text(json.dumps(base_env, sort_keys=True) + "\n", encoding="utf-8")
client.commit_module(root_dir=root, module_path=root / "module_env_base.json", config=root / "env_heldout.toml")

# Promote safe candidates

def write_candidate_module(path: Path, payload: dict) -> None:
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": (root / "ledger" / "head").read_text(encoding="utf-8").strip(),
        "payload": payload,
    }
    path.write_text(json.dumps(module, sort_keys=True) + "\n", encoding="utf-8")

tooluse_candidate_payload = {
    "new_symbols": ["tooluse_candidate"],
    "definitions": [
        {
            "name": "tooluse_candidate",
            "params": [
                {"name": "step", "type": {"tag": "int"}},
                {"name": "last_ok", "type": {"tag": "int"}},
                {"name": "last_len", "type": {"tag": "int"}},
            ],
            "ret_type": {"tag": "int"},
            "body": tooluse_policy_body([0, 1]),
            "termination": {"kind": "structural", "decreases_param": None},
        }
    ],
    "declared_deps": ["tooluse_base", "tooluse_oracle"],
    "specs": [],
    "concepts": [{"concept": "tooluse.file_transform", "symbol": "tooluse_candidate"}],
}

env_candidate_payload = {
    "new_symbols": ["env_candidate"],
    "definitions": [
        {
            "name": "env_candidate",
            "params": [
                {"name": "agent_x", "type": {"tag": "int"}},
                {"name": "agent_y", "type": {"tag": "int"}},
                {"name": "goal_x", "type": {"tag": "int"}},
                {"name": "goal_y", "type": {"tag": "int"}},
            ],
            "ret_type": {"tag": "int"},
            "body": env_greedy_body(),
            "termination": {"kind": "structural", "decreases_param": None},
        }
    ],
    "declared_deps": ["env_base", "env_oracle"],
    "specs": [],
    "concepts": [{"concept": "gridworld", "symbol": "env_candidate"}],
}

tooluse_candidate_module = root / "module_tooluse_candidate.json"
env_candidate_module = root / "module_env_candidate.json"
write_candidate_module(tooluse_candidate_module, tooluse_candidate_payload)
write_candidate_module(env_candidate_module, env_candidate_payload)

promote_tooluse = promote_candidate(
    client=client,
    root_dir=root,
    concept="tooluse.file_transform",
    baseline="tooluse_base",
    oracle="tooluse_oracle",
    candidate=Candidate(name="tooluse_candidate", proposer="capstone", payload=tooluse_candidate_payload),
    dev_config=root / "tooluse_dev.toml",
    heldout_config=root / "tooluse_heldout.toml",
    heldout_suites_dir=heldout_dir,
    safety_config=root / "tooluse_safety_good.toml",
    safety_suites_dir=heldout_dir,
    constraint_spec_path=Path(os.environ["ROOT_DIR"]) / "constraints" / "tooluse_constraint_spec_v1.json",
    seed_key="sealed-seed",
    min_dev_diff_sum=1,
    out_dir=run_dir / "tooluse_promo",
)

promote_env = promote_candidate(
    client=client,
    root_dir=root,
    concept="gridworld",
    baseline="env_base",
    oracle="env_oracle",
    candidate=Candidate(name="env_candidate", proposer="capstone", payload=env_candidate_payload),
    dev_config=root / "env_dev.toml",
    heldout_config=root / "env_heldout.toml",
    heldout_suites_dir=heldout_dir,
    safety_config=root / "env_safety.toml",
    safety_suites_dir=heldout_dir,
    constraint_spec_path=Path(os.environ["ROOT_DIR"]) / "constraints" / "env_constraint_spec_v1.json",
    seed_key="sealed-seed",
    min_dev_diff_sum=1,
    out_dir=run_dir / "env_promo",
)

plan_dir = root / "plan_skills"
plan_dir.mkdir(parents=True, exist_ok=True)
plan_skill = build_plan_skill(
    task_id="gridworld",
    steps=[
        PlanStep(
            step_idx=0,
            kind="skill",
            name="env_oracle",
            args={"inputs": {}},
        )
    ],
    dependencies=["env_oracle"],
    constraints={"domain": "env", "concept": "gridworld", "max_steps": 10},
    example_traces=[],
)
plan_path = plan_dir / f"{plan_skill['plan_id']}.json"
plan_path.write_text(json.dumps(plan_skill, sort_keys=True) + "\n", encoding="utf-8")

agent = AgentProposer(root_dir=root, config_path=root / "env_hard_heldout.toml", run_dir=run_dir / "env_hard_agent")
agent_bundle = ContextBundle(
    concept="gridworld",
    baseline_symbol="env_base",
    oracle_symbol="env_oracle",
    type_norm="Int->Int->Int->Int->Int",
    symbols=[],
)
agent_candidates = agent.propose(context=agent_bundle, budget=1, rng_seed=17)
if not agent_candidates:
    raise RuntimeError("env hard agent proposer produced no candidates")
env_hard_agent = agent_candidates[0]
env_hard_agent_module = root / "module_env_hard_agent.json"
write_candidate_module(env_hard_agent_module, env_hard_agent.payload)

# Unsafe candidate should be blocked by safety suite
unsafe_result = promote_candidate(
    client=client,
    root_dir=root,
    concept="tooluse.file_transform",
    baseline="tooluse_base",
    oracle="tooluse_oracle",
    candidate=Candidate(name="tooluse_candidate", proposer="capstone", payload=tooluse_candidate_payload),
    dev_config=root / "tooluse_dev.toml",
    heldout_config=root / "tooluse_heldout.toml",
    heldout_suites_dir=heldout_dir,
    safety_config=root / "tooluse_safety_bad.toml",
    safety_suites_dir=heldout_dir,
    constraint_spec_path=Path(os.environ["ROOT_DIR"]) / "constraints" / "tooluse_constraint_spec_v1.json",
    seed_key="sealed-seed",
    min_dev_diff_sum=1,
    out_dir=run_dir / "tooluse_unsafe",
)


def heldout_cert(
    *,
    concept: str,
    baseline: str,
    candidate: str,
    oracle: str,
    config_path: Path,
    candidate_module: Path | None = None,
) -> dict:
    cfg = load_config_from_path(root, config_path)
    sealed_cfg = load_sealed_config(cfg.data, require_keys=False)
    episodes = int((cfg.data.get("sealed") or {}).get("episodes", 1))
    max_steps = int((cfg.data.get("evaluator") or {}).get("step_limit", 100000))
    request = {
        "kind": "stat_cert",
        "concept": concept,
        "metric": "accuracy",
        "null": "no_improvement",
        "baseline_symbol": baseline,
        "candidate_symbol": candidate,
        "eval": {
            "episodes": episodes,
            "max_steps": max_steps,
            "paired_seeds": True,
            "oracle_symbol": oracle,
        },
        "risk": {"evalue_threshold": "1"},
    }
    req_path = run_dir / f"{concept}_heldout_request.json"
    cert_path = run_dir / f"{concept}_heldout_cert.json"
    req_path.write_text(json.dumps(request, sort_keys=True) + "\n", encoding="utf-8")
    client.issue_stat_cert(
        root_dir=root,
        request_path=req_path,
        out_path=cert_path,
        config=config_path,
        seed_key="sealed-seed",
        suites_dir=heldout_dir,
        candidate_module=candidate_module,
    )
    return json.loads(cert_path.read_text(encoding="utf-8"))


def rates_from_cert(cert: dict) -> tuple[float, float]:
    payload = cert.get("certificate") or {}
    n = int(payload.get("n", 1))
    base = int(payload.get("baseline_successes", 0))
    cand = int(payload.get("candidate_successes", 0))
    return base / n, cand / n


tooluse_cert = heldout_cert(
    concept="tooluse.file_transform",
    baseline="tooluse_base",
    candidate="tooluse_candidate",
    oracle="tooluse_oracle",
    config_path=root / "tooluse_heldout.toml",
    candidate_module=tooluse_candidate_module,
)

env_cert = heldout_cert(
    concept="gridworld",
    baseline="env_base",
    candidate="env_candidate",
    oracle="env_oracle",
    config_path=root / "env_heldout.toml",
    candidate_module=env_candidate_module,
)

env_hard_cert = heldout_cert(
    concept="gridworld",
    baseline="env_base",
    candidate=env_hard_agent.name,
    oracle="env_oracle",
    config_path=root / "env_hard_heldout.toml",
    candidate_module=env_hard_agent_module,
)

baseline_tooluse_rate, candidate_tooluse_rate = rates_from_cert(tooluse_cert)
baseline_env_rate, candidate_env_rate = rates_from_cert(env_cert)
baseline_env_hard_rate, candidate_env_hard_rate = rates_from_cert(env_hard_cert)

summary = {
    "run_id": os.environ["RUN_ID"],
    "tooluse": {
        "heldout_suite_hash": cap_heldout_hash,
        "baseline_success_rate": baseline_tooluse_rate,
        "library_success_rate": candidate_tooluse_rate,
        "adopted": promote_tooluse.accepted,
        "adoption_hash": promote_tooluse.adoption_hash,
    },
    "env": {
        "heldout_suite_hash": env_heldout_hash,
        "baseline_success_rate": baseline_env_rate,
        "library_success_rate": candidate_env_rate,
        "adopted": promote_env.accepted,
        "adoption_hash": promote_env.adoption_hash,
    },
    "env_hard": {
        "heldout_suite_hash": env_hard_heldout_hash,
        "baseline_success_rate": baseline_env_hard_rate,
        "library_success_rate": candidate_env_hard_rate,
        "agent_candidate": env_hard_agent.name,
    },
    "safety_gate": {
        "unsafe_candidate_blocked": not unsafe_result.accepted,
        "unsafe_reason": unsafe_result.reason,
    },
}

summary_path = run_dir / "capstone_ae_summary.json"
summary_path.write_text(json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
print(summary_path)
PY
