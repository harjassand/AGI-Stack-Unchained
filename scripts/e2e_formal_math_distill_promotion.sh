#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
CDEL_ROOT="$ROOT/CDEL-v2"
ORCH_ROOT="$ROOT/Extension-1/agi-orchestrator"
AGI_ROOT="$ROOT/agi-system/agi-system"
export ROOT

if [[ -z "${E2E_SHADOW_TASKS:-}" && -z "${E2E_SHADOW_TASK_MULTIPLIER:-}" ]]; then
  export E2E_SHADOW_TASK_MULTIPLIER=2
fi

RUN_ROOT="$(mktemp -d)"
export RUN_ROOT
CDEL_STATE_DIR="$RUN_ROOT/cdel_state"
export CDEL_STATE_DIR
E2E_EPOCH_ID="${E2E_EPOCH_ID:-epoch-distill}"
SEEDS_PATH="$RUN_ROOT/seeds.jsonl"
BASELINE_CAPSULE="$RUN_ROOT/baseline_capsule.json"
SERVER_INFO="$RUN_ROOT/server.json"
HELDOUT_CONFIG="$RUN_ROOT/heldout_config.toml"
SAFETY_CONFIG="$RUN_ROOT/safety_config.toml"
DEV_CONFIG="$CDEL_ROOT/configs/sealed_formal_math_dev.toml"
export SEEDS_PATH
export BASELINE_CAPSULE
export SERVER_INFO

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
  if [[ "${KEEP_RUN_ROOT:-}" != "1" ]]; then
    rm -rf "$RUN_ROOT"
  else
    echo "KEEP_RUN_ROOT=1 set; preserving $RUN_ROOT"
  fi
}
trap cleanup EXIT

if [[ -z "${CDEL_SUITES_DIR:-}" ]]; then
  echo "CDEL_SUITES_DIR must be set (contains sealed heldout + safety suites)." 1>&2
  exit 1
fi
if [[ -z "${FORMAL_MATH_HELDOUT_HASH:-}" || -z "${FORMAL_MATH_SAFETY_HASH:-}" ]]; then
  echo "FORMAL_MATH_HELDOUT_HASH and FORMAL_MATH_SAFETY_HASH must be set." 1>&2
  exit 1
fi

MISSING_HELDOUT_SUITES=0
if [[ ! -d "$CDEL_SUITES_DIR/formal_math_v1/$FORMAL_MATH_HELDOUT_HASH" ]]; then
  echo "Heldout suite not found in CDEL_SUITES_DIR/formal_math_v1/$FORMAL_MATH_HELDOUT_HASH" 1>&2
  MISSING_HELDOUT_SUITES=1
fi
if [[ ! -d "$CDEL_SUITES_DIR/formal_math_v1/safety/$FORMAL_MATH_SAFETY_HASH" ]]; then
  echo "Safety suite not found in CDEL_SUITES_DIR/formal_math_v1/safety/$FORMAL_MATH_SAFETY_HASH" 1>&2
  MISSING_HELDOUT_SUITES=1
fi
export MISSING_HELDOUT_SUITES

HELDOUT_EPISODES=0
SAFETY_EPISODES=0
if [[ "$MISSING_HELDOUT_SUITES" -eq 0 ]]; then
  HELDOUT_EPISODES=$(python3 - <<'PY'
import os
from pathlib import Path

suite_hash = os.environ["FORMAL_MATH_HELDOUT_HASH"]
base = Path(os.environ["CDEL_SUITES_DIR"]) / "formal_math_v1" / suite_hash / "suite.jsonl"
if not base.exists():
    print(0)
else:
    count = 0
    for line in base.read_text(encoding="utf-8").splitlines():
        if line.strip():
            count += 1
    print(count)
PY
)
  SAFETY_EPISODES=$(python3 - <<'PY'
import os
from pathlib import Path

suite_hash = os.environ["FORMAL_MATH_SAFETY_HASH"]
base = Path(os.environ["CDEL_SUITES_DIR"]) / "formal_math_v1" / "safety" / suite_hash / "suite.jsonl"
if not base.exists():
    print(0)
else:
    count = 0
    for line in base.read_text(encoding="utf-8").splitlines():
        if line.strip():
            count += 1
    print(count)
PY
)
  if [[ "$HELDOUT_EPISODES" -le 0 ]]; then
    echo "Heldout suite has no episodes" 1>&2
    MISSING_HELDOUT_SUITES=1
  fi
  if [[ "$SAFETY_EPISODES" -le 0 ]]; then
    echo "Safety suite has no episodes" 1>&2
    MISSING_HELDOUT_SUITES=1
  fi
  export MISSING_HELDOUT_SUITES
fi
if [[ "$HELDOUT_EPISODES" -le 0 ]]; then
  HELDOUT_EPISODES=1
fi
if [[ "$SAFETY_EPISODES" -le 0 ]]; then
  SAFETY_EPISODES=1
fi

echo '{"seed":0}' > "$SEEDS_PATH"

KEY_JSON=$(python3 - <<'PY'
import json
from cdel.sealed.crypto import generate_keypair
priv, pub = generate_keypair()
print(json.dumps({"priv": priv, "pub": pub}))
PY
)
export KEY_JSON
CDEL_RECEIPT_PRIVKEY=$(python3 - <<'PY'
import json, os
print(json.loads(os.environ["KEY_JSON"])["priv"])
PY
)
CDEL_RECEIPT_PUBKEY=$(python3 - <<'PY'
import json, os
print(json.loads(os.environ["KEY_JSON"])["pub"])
PY
)
export CDEL_RECEIPT_PRIVKEY
export CDEL_RECEIPT_PUBKEY
export CDEL_REQUIRE_ED25519_RECEIPT=1
if [[ -z "${CDEL_SEALED_SEED:-}" ]]; then
  CDEL_SEALED_SEED=$(python3 - <<'PY'
import os
print(os.urandom(32).hex())
PY
)
  export CDEL_SEALED_SEED
fi

export AGI_SYSTEM_ROOT="$AGI_ROOT"
if [[ -n "${PYTHONPATH:-}" ]]; then
  export PYTHONPATH="$AGI_ROOT:$PYTHONPATH"
else
  export PYTHONPATH="$AGI_ROOT"
fi
if [[ -z "${ELAN_HOME:-}" && -d "$HOME/.elan" ]]; then
  export ELAN_HOME="$HOME/.elan"
fi
if [[ -z "${LEAN_PATH:-}" ]]; then
  if command -v lean >/dev/null 2>&1; then
    LEAN_PATH_CANDIDATE=$(lean --print-libdir 2>/dev/null || true)
    if [[ -n "$LEAN_PATH_CANDIDATE" ]]; then
      export LEAN_PATH="$LEAN_PATH_CANDIDATE"
    fi
  fi
fi
BASELINE_COMPONENTS_DIR=$(python3 - <<'PY'
import json
import os
from pathlib import Path
from orchestrator.system_components import load_or_init_manifest
from orchestrator import json_utils

run_root = Path(os.environ["RUN_ROOT"]).resolve()
eval_suite_hash = os.environ["FORMAL_MATH_HELDOUT_HASH"]
manifest = load_or_init_manifest(root_dir=run_root, eval_suite_hash=eval_suite_hash, episodes=8)
Path(os.environ["BASELINE_CAPSULE"]).write_text(
    json_utils.dumps(manifest.system_capsule, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(str(manifest.components_dir))
PY
)

export CDEL_COMPONENTS_DIR="$BASELINE_COMPONENTS_DIR"
export FORMAL_MATH_E2E_SEED_TEMPLATES="${FORMAL_MATH_E2E_SEED_TEMPLATES:-1}"

DEV_SUITES_DIR="$RUN_ROOT/dev_suites"
export DEV_SUITES_DIR
mkdir -p "$DEV_SUITES_DIR"
DEV_COMBINED_HASH=$(python3 - <<'PY'
import os
from pathlib import Path
from blake3 import blake3

root = Path(os.environ["ROOT"]).resolve()
out_dir = Path(os.environ["DEV_SUITES_DIR"]).resolve()
suite_dir = root / "agi-system" / "agi-system" / "system_runtime" / "suites" / "formal_math_v1" / "dev"
easy_path = suite_dir / "fm_easy.jsonl"
mid_path = suite_dir / "fm_mid.jsonl"
shifted_path = suite_dir / "fm_shifted.jsonl"
easy_data = easy_path.read_bytes() if easy_path.exists() else b""
mid_data = mid_path.read_bytes() if mid_path.exists() else b""
combined = mid_data + easy_data if mid_data else easy_data
combined_hash = blake3(combined).hexdigest()
(out_dir / f"{combined_hash}.jsonl").write_bytes(combined)
if shifted_path.exists():
    shifted_data = shifted_path.read_bytes()
    shifted_hash = blake3(shifted_data).hexdigest()
    (out_dir / f"{shifted_hash}.jsonl").write_bytes(shifted_data)
print(combined_hash)
PY
)
export DEV_COMBINED_HASH

if [[ -n "${E2E_SHADOW_TASKS:-}" || -n "${E2E_SHADOW_TASK_MULTIPLIER:-}" ]]; then
  BASE_EPISODES=$(python3 - <<'PY'
from pathlib import Path
import os
import tomllib

root = Path(os.environ["ROOT"]).resolve()
cfg_path = root / "CDEL-v2" / "configs" / "sealed_formal_math_dev.toml"
data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
episodes = int((data.get("sealed") or {}).get("episodes", 0) or 0)
print(episodes)
PY
)
  if [[ -n "${E2E_SHADOW_TASKS:-}" ]]; then
    EPISODES="$E2E_SHADOW_TASKS"
  else
    MULT="${E2E_SHADOW_TASK_MULTIPLIER}"
    EPISODES=$((BASE_EPISODES * MULT))
  fi
  if [[ "$EPISODES" -le 0 ]]; then
    echo "Invalid episode override for dev config" 1>&2
    exit 1
  fi
  SUITE_PATH="$DEV_SUITES_DIR/$DEV_COMBINED_HASH.jsonl"
  if [[ -f "$SUITE_PATH" ]]; then
    SUITE_COUNT=$(wc -l < "$SUITE_PATH" | tr -d ' ')
    if [[ "$SUITE_COUNT" -gt 0 && "$EPISODES" -gt "$SUITE_COUNT" ]]; then
      EPISODES="$SUITE_COUNT"
    fi
  fi
  DEV_CONFIG="$RUN_ROOT/sealed_formal_math_dev.toml"
  cat > "$DEV_CONFIG" <<EOF
[sealed]
eval_harness_id = "system-harness-v1"
eval_harness_hash = "system-harness-v1-hash"
eval_suite_hash = "$DEV_COMBINED_HASH"
episodes = $EPISODES
EOF
fi

cat > "$HELDOUT_CONFIG" <<EOF
[sealed]
alpha_total = "0.01"
alpha_schedule = { name = "p_series", exponent = 2, coefficient = "0.4" }
eval_harness_id = "system-harness-v1"
eval_harness_hash = "system-harness-v1-hash"
eval_suite_hash = "$FORMAL_MATH_HELDOUT_HASH"
episodes = $HELDOUT_EPISODES
EOF

cat > "$SAFETY_CONFIG" <<EOF
[sealed]
alpha_total = "0.01"
alpha_schedule = { name = "p_series", exponent = 2, coefficient = "0.4" }
eval_harness_id = "system-harness-v1"
eval_harness_hash = "system-harness-v1-hash"
eval_suite_hash = "$FORMAL_MATH_SAFETY_HASH"
episodes = $SAFETY_EPISODES
EOF

if [[ "$MISSING_HELDOUT_SUITES" -eq 0 ]]; then
  SHIFT_PACK="${FORMAL_MATH_SHIFT_PACK:-formal_math_v2}"
  export SHIFT_PACK
  SHIFT_IDS=$(python3 - <<'PY'
import os

pack = os.environ.get("SHIFT_PACK", "formal_math_v2")
if pack == "formal_math_v2":
    from system_runtime.shifts.v2.formal_math import shift_ids  # type: ignore
    print("\n".join(shift_ids()))
else:
    from system_runtime.shifts.v1 import shift_ids  # type: ignore
    print("\n".join(shift_ids()))
PY
)

  while IFS= read -r shift_id; do
    if [[ -z "$shift_id" ]]; then
      continue
    fi
    python3 -m cdel.cli baseline precompute \
      --epoch "$E2E_EPOCH_ID" \
      --suite "$FORMAL_MATH_HELDOUT_HASH" \
      --seeds "$SEEDS_PATH" \
      --baseline-capsule "$BASELINE_CAPSULE" \
      --shift-id "$shift_id" \
      --fixture-dir "$CDEL_ROOT"

    python3 -m cdel.cli baseline precompute \
      --epoch "$E2E_EPOCH_ID" \
      --suite "$FORMAL_MATH_SAFETY_HASH" \
      --seeds "$SEEDS_PATH" \
      --baseline-capsule "$BASELINE_CAPSULE" \
      --shift-id "$shift_id" \
      --suite-kind safety \
      --fixture-dir "$CDEL_ROOT"
  done <<< "$SHIFT_IDS"
fi

python3 -m cdel.evaluate_service.app \
  --host 127.0.0.1 \
  --port 0 \
  --ledger-dir "$RUN_ROOT/ledger" \
  --fixture-dir "$CDEL_ROOT" \
  --server-info-file "$SERVER_INFO" &
SERVER_PID=$!

for _ in {1..50}; do
  if [[ -f "$SERVER_INFO" ]]; then
    break
  fi
  sleep 0.1
done
if [[ ! -f "$SERVER_INFO" ]]; then
  echo "Evaluate service failed to start" 1>&2
  exit 1
fi

BASE_URL=$(python3 - <<'PY'
import json, os
info = json.loads(open(os.environ["SERVER_INFO"], "r", encoding="utf-8").read())
print(info["base_url"])
PY
)

python3 -m orchestrator.run \
  --domain formal-math-v1 \
  --root "$RUN_ROOT" \
  --dev-config "$DEV_CONFIG" \
  --heldout-config "$HELDOUT_CONFIG" \
  --safety-config "$SAFETY_CONFIG" \
  --evaluate-url "$BASE_URL" \
  --epoch-id "$E2E_EPOCH_ID" \
  --proposers formal_math_distill_v1 \
  --shadow-eta 0.2 \
  --shadow-k 1 \
  --shadow-mode operator_only \
  --no-shadow-require-shifts \
  --no-shadow-require-attribution \
  --shadow-suites-dir "$DEV_SUITES_DIR" \
  --rng-seed 1 \
  --runs-dir "$RUN_ROOT/runs"

python3 - <<'PY'
import json
import os
from pathlib import Path
from cdel.receipt_verify import verify_receipt

runs_dir = Path(os.environ["RUN_ROOT"]) / "runs"
run_dirs = sorted(p for p in runs_dir.iterdir() if p.is_dir())
if not run_dirs:
    raise SystemExit("no run output found")
manifest = json.loads((run_dirs[-1] / "manifest.json").read_text(encoding="utf-8"))
attempts = manifest.get("attempts") or []
if not attempts:
    raise SystemExit("no attempts logged")
last_attempt = attempts[-1]
heldout_status = last_attempt.get("heldout_eval_status")
if not heldout_status or heldout_status == "not_attempted":
    reason = manifest.get("reason")
    raise SystemExit(f"E2E FAILED: heldout not attempted (reason: {reason})")

capsule_hash = last_attempt.get("capsule_hash") or manifest.get("baseline_capsule_hash")
if not capsule_hash:
    raise SystemExit("missing capsule hash for receipt verification")

require_pass = os.environ.get("EXPECT_HELDOUT_PASS") == "1" or os.environ.get("REQUIRE_PASS") == "1"
receipt = last_attempt.get("receipt")
heldout_http_status = last_attempt.get("heldout_http_status")
heldout_reason = last_attempt.get("heldout_reason")
missing_suites = os.environ.get("MISSING_HELDOUT_SUITES") == "1"

heldout_result = "INVALID"
heldout_response = None
heldout_classification = "INFRA_HTTP_ERROR"

if heldout_status == "attempted_pass":
    heldout_result = "PASS"
    if isinstance(receipt, dict):
        heldout_response = {"result": "PASS", "receipt": receipt}
        if heldout_http_status == 200:
            ok, reason = verify_receipt(
                receipt,
                expected_capsule_hash=capsule_hash,
                expected_epoch_id=manifest.get("epoch_id"),
                public_key=os.environ["CDEL_RECEIPT_PUBKEY"],
            )
            if not ok:
                raise SystemExit(f"receipt verification failed: {reason}")
            heldout_classification = "EVAL_PASS"
        else:
            heldout_classification = "INFRA_HTTP_ERROR"
    else:
        heldout_classification = "INFRA_SCHEMA_VIOLATION"
elif heldout_status == "attempted_fail":
    heldout_result = "FAIL"
    if heldout_http_status == 200:
        heldout_response = {"result": "FAIL"}
        heldout_classification = "EVAL_FAIL"
    elif heldout_reason == "heldout_invalid_envelope":
        heldout_classification = "INFRA_SCHEMA_VIOLATION"
    else:
        heldout_classification = "INFRA_HTTP_ERROR"
elif heldout_status == "attempted_refused_ledger":
    heldout_result = "REFUSED"
    if heldout_http_status == 429:
        heldout_response = {"result": "REFUSED"}
        heldout_classification = "EVAL_REFUSED"
    else:
        heldout_classification = "INFRA_HTTP_ERROR"
elif heldout_status == "attempted_error" and heldout_reason == "heldout_invalid_envelope":
    heldout_classification = "INFRA_SCHEMA_VIOLATION"

classification_path = run_dirs[-1] / "heldout_classification.json"
classification_payload = {
    "heldout_http_status": heldout_http_status,
    "heldout_response_json": heldout_response,
    "heldout_result": heldout_result,
    "heldout_classification": heldout_classification,
}
classification_path.write_text(json.dumps(classification_payload, sort_keys=True) + "\n", encoding="utf-8")

if missing_suites:
    heldout_classification = "INFRA_SCHEMA_VIOLATION"
    classification_payload["heldout_classification"] = heldout_classification
    classification_path.write_text(json.dumps(classification_payload, sort_keys=True) + "\n", encoding="utf-8")
    raise SystemExit(f"E2E FAILED: {heldout_classification}")
if heldout_classification.startswith("INFRA_"):
    raise SystemExit(f"E2E FAILED: {heldout_classification}")
if require_pass and heldout_classification != "EVAL_PASS":
    raise SystemExit("heldout PASS required but not achieved")

print(f"heldout_eval_status={heldout_status}")
print(f"heldout_classification={heldout_classification}")
print("formal_math distill promotion demo complete")
PY

kill "$SERVER_PID" >/dev/null 2>&1 || true
