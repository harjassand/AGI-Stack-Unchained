#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
CDEL_ROOT="$ROOT/CDEL-v2"
ORCH_ROOT="$ROOT/Extension-1/agi-orchestrator"
AGI_ROOT="$ROOT/agi-system/agi-system"

DEV_SUITE_HASH="eeca17f858692d2b536f86b484fb530130e680cee92c53239cb1e30e15125c63"
SAFETY_SUITE_HASH="eae791c9563e5a54292bd019c863a40e09e8891a5a2424e91c0143f7a55fcc96"

RUN_ROOT="$(mktemp -d)"
SEEDS_PATH="$RUN_ROOT/seeds.jsonl"
BASELINE_CAPSULE="$RUN_ROOT/baseline_capsule.json"
SERVER_INFO="$RUN_ROOT/server.json"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
  rm -rf "$RUN_ROOT"
}
trap cleanup EXIT

echo '{"seed":0}' > "$SEEDS_PATH"

# Set up heldout suites dir (dev-heldout fallback is opt-in only).
HELDOUT_DIR="${HELDOUT_SUITES_DIR:-}"
FALLBACK_USED=0
if [[ -z "$HELDOUT_DIR" ]]; then
  if [[ "${ALLOW_DEV_HELDOUT_FALLBACK:-}" != "1" ]]; then
    echo "HELDOUT_SUITES_DIR is required. Set ALLOW_DEV_HELDOUT_FALLBACK=1 for dev-only demo." 1>&2
    exit 1
  fi
  echo "WARNING: using dev-heldout fallback (not a real heldout run)." 1>&2
  HELDOUT_DIR="$(mktemp -d)"
  FALLBACK_USED=1
  mkdir -p "$HELDOUT_DIR/safety"
  cp "$CDEL_ROOT/sealed_suites/${DEV_SUITE_HASH}.jsonl" "$HELDOUT_DIR/${DEV_SUITE_HASH}.jsonl"
  cp "$CDEL_ROOT/sealed_suites/safety/${SAFETY_SUITE_HASH}.jsonl" "$HELDOUT_DIR/safety/${SAFETY_SUITE_HASH}.jsonl"
fi

# Ephemeral receipt keys (no logging).
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
print(json.loads(os.environ["KEY_JSON"])['priv'])
PY
)
CDEL_RECEIPT_PUBKEY=$(python3 - <<'PY'
import json, os
print(json.loads(os.environ["KEY_JSON"])['pub'])
PY
)

export CDEL_RECEIPT_PRIVKEY
export CDEL_RECEIPT_PUBKEY
export CDEL_REQUIRE_ED25519_RECEIPT=1

# Build baseline SYSTEM capsule and component store under RUN_ROOT.
export RUN_ROOT
export DEV_SUITE_HASH
export BASELINE_CAPSULE
export AGI_SYSTEM_ROOT="$AGI_ROOT"
BASELINE_COMPONENTS_DIR=$(python3 - <<'PY'
import json
import os
from pathlib import Path
from orchestrator.system_components import load_or_init_manifest

run_root = Path(os.environ["RUN_ROOT"]).resolve()
eval_suite_hash = os.environ["DEV_SUITE_HASH"]
manifest = load_or_init_manifest(root_dir=run_root, eval_suite_hash=eval_suite_hash, episodes=5)
Path(os.environ["BASELINE_CAPSULE"]).write_text(
    json.dumps(manifest.system_capsule, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(str(manifest.components_dir))
PY
)

export CDEL_COMPONENTS_DIR="$BASELINE_COMPONENTS_DIR"

# Precompute baseline caches (capability + safety).
python3 -m cdel.cli baseline precompute \
  --epoch "epoch-smoke" \
  --suite "$DEV_SUITE_HASH" \
  --seeds "$SEEDS_PATH" \
  --baseline-capsule "$BASELINE_CAPSULE" \
  --shift-id identity \
  --fixture-dir "$CDEL_ROOT"

python3 -m cdel.cli baseline precompute \
  --epoch "epoch-smoke" \
  --suite "$SAFETY_SUITE_HASH" \
  --seeds "$SEEDS_PATH" \
  --baseline-capsule "$BASELINE_CAPSULE" \
  --shift-id identity \
  --suite-kind safety \
  --fixture-dir "$CDEL_ROOT"

# Start Evaluate service (heldout in CDEL only).
export CDEL_SUITES_DIR="$HELDOUT_DIR"
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

# Run orchestrator dev->heldout loop for formal math.
python3 -m orchestrator.run \
  --domain formal-math-v1 \
  --root "$RUN_ROOT" \
  --dev-config "$CDEL_ROOT/configs/sealed_formal_math_dev.toml" \
  --heldout-config "$CDEL_ROOT/configs/smoke_formal_math_heldout.toml" \
  --evaluate-url "$BASE_URL" \
  --epoch-id "epoch-smoke" \
  --proposers system_component \
  --shadow-eta 0.2 \
  --shadow-k 1 \
  --shadow-mode operator_only \
  --no-shadow-require-shifts \
  --no-shadow-require-attribution \
  --shadow-suites-dir "$CDEL_ROOT/sealed_suites" \
  --rng-seed 1 \
  --runs-dir "$RUN_ROOT/runs"

# Verify receipt in manifest.
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
last_attempt = (manifest.get("attempts") or [])[-1] if manifest.get("attempts") else {}
receipt = last_attempt.get("receipt")
if not receipt:
    raise SystemExit("missing receipt in manifest")

capsule_hash = last_attempt.get("capsule_hash") or manifest.get("baseline_capsule_hash")
if not capsule_hash:
    raise SystemExit("missing capsule hash for receipt verification")

ok, reason = verify_receipt(
    receipt,
    expected_capsule_hash=capsule_hash,
    expected_epoch_id=manifest.get("epoch_id"),
    public_key=os.environ["CDEL_RECEIPT_PUBKEY"],
)
if not ok:
    raise SystemExit(f"receipt verification failed: {reason}")

print("formal_math promotion demo complete")
PY

kill "$SERVER_PID" >/dev/null 2>&1 || true

if [[ "$FALLBACK_USED" == "1" ]]; then
  rm -rf "$HELDOUT_DIR"
fi
