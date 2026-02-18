#!/usr/bin/env bash
set -u -o pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

CAMPAIGN_PACK="${OMEGA_IGNITE_CAMPAIGN_PACK:-campaigns/rsi_omega_daemon_v19_0_super_unified/rsi_omega_daemon_pack_v1.json}"
START_TICK="${OMEGA_IGNITE_START_TICK:-1}"
OUT_ROOT="${OMEGA_IGNITE_OUT_ROOT:-runs/ignite_v19_super_unified}"
LOG_PATH="${OMEGA_IGNITE_LOG_PATH:-runaway_evolution.log}"
SLEEP_SECONDS="${OMEGA_IGNITE_SLEEP_SECONDS:-1}"
ACTIVATION_MODE="${OMEGA_META_CORE_ACTIVATION_MODE:-simulate}"
ALLOW_SIMULATE="${OMEGA_ALLOW_SIMULATE_ACTIVATION:-1}"
WORKTREE_DIR="${OMEGA_IGNITE_WORKTREE_DIR:-${OUT_ROOT}/_worktree}"
APPLY_TARGETS_CSV="${OMEGA_IGNITE_APPLY_TARGETS:-orchestrator/omega_v19_0/coordinator_v1.py,orchestrator/omega_bid_market_v1.py}"
GOOGLE_API_KEY_FILE_DEFAULT="${HOME}/.config/omega/google_api_key"
GOOGLE_API_KEY_FILE="${OMEGA_GOOGLE_API_KEY_FILE:-${GOOGLE_API_KEY_FILE_DEFAULT}}"

if ! [[ "$START_TICK" =~ ^[0-9]+$ ]]; then
  echo "OMEGA_IGNITE_START_TICK must be an unsigned integer" >&2
  exit 2
fi
if ! [[ "$SLEEP_SECONDS" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "OMEGA_IGNITE_SLEEP_SECONDS must be numeric" >&2
  exit 2
fi

RAW_ROOT="${OUT_ROOT}/raw"
# Normalize OUT_ROOT + LOG_PATH to absolute paths so running inside a git worktree keeps evidence rooted.
mkdir -p "$OUT_ROOT"
OUT_ROOT="$(cd "$OUT_ROOT" && pwd)"
RAW_ROOT="${OUT_ROOT}/raw"
mkdir -p "$RAW_ROOT"
if [[ "${LOG_PATH:0:1}" != "/" ]]; then
  LOG_PATH="${ROOT}/${LOG_PATH}"
fi
mkdir -p "$(dirname "$LOG_PATH")"

if [[ "${WORKTREE_DIR:0:1}" != "/" ]]; then
  WORKTREE_DIR="${ROOT}/${WORKTREE_DIR}"
fi

ensure_worktree() {
  local worktree_dir="$1"
  mkdir -p "$(dirname "$worktree_dir")"
  if git -C "$worktree_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return 0
  fi
  rm -rf "$worktree_dir"
  if ! git -C "$ROOT" worktree add --detach "$worktree_dir" HEAD >/dev/null 2>&1; then
    git -C "$ROOT" worktree prune >/dev/null 2>&1 || true
    git -C "$ROOT" worktree add --detach "$worktree_dir" HEAD >/dev/null
  fi
}

ensure_worktree "$WORKTREE_DIR"

ignite_on_success() {
  local tick_u64="$1"
  local state_dir="$2"
  local raw_log="$3"
  python3 - "$tick_u64" "$state_dir" "$OUT_ROOT" "$WORKTREE_DIR" "$APPLY_TARGETS_CSV" "$raw_log" <<'PY'
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

tick_u64 = int(sys.argv[1])
state_dir = Path(sys.argv[2]).resolve()
out_root = Path(sys.argv[3]).resolve()
worktree_dir = Path(sys.argv[4]).resolve()
apply_targets_csv = str(sys.argv[5])
raw_log = Path(sys.argv[6]).resolve()

ignite_dir = out_root / "_ignite"
ignite_dir.mkdir(parents=True, exist_ok=True)
state_path = ignite_dir / "ignite_code_activation_state_v1.json"
active_ptr = ignite_dir / "ACTIVE_CODE_ACTIVATION_KEY"
prev_ptr = ignite_dir / "PREV_ACTIVE_CODE_ACTIVATION_KEY"
activation_map = ignite_dir / "activation_map_v1.jsonl"
landings_dir = ignite_dir / "landings"
landings_dir.mkdir(parents=True, exist_ok=True)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(args: list[str]) -> str:
    run = subprocess.run(["git", "-C", str(worktree_dir), *args], capture_output=True, text=True, check=False)
    if run.returncode != 0:
        raise RuntimeError((run.stderr or run.stdout or "git failed").strip())
    return (run.stdout or "").strip()


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    _atomic_write_text(path, text)


def _ensure_activation_state() -> dict[str, Any]:
    head = _git(["rev-parse", "HEAD"])
    if state_path.exists():
        existing = _load_json(state_path)
        if isinstance(existing, dict) and str(existing.get("schema_version", "")) == "ignite_code_activation_state_v1":
            return existing
    bootstrap_key = "BOOTSTRAP"
    _atomic_write_text(active_ptr, bootstrap_key + "\n")
    _atomic_write_text(prev_ptr, bootstrap_key + "\n")
    payload = {
        "schema_version": "ignite_code_activation_state_v1",
        "last_stable": {
            "activation_key": bootstrap_key,
            "git_sha": head,
            "tick_u64": int(max(0, tick_u64 - 1)),
            "ccap_id": None,
            "bundle_hash": None,
            "patch_sha256": None,
        },
        "pending": None,
    }
    _atomic_write_json(state_path, payload)
    return payload


def _append_map(event: dict[str, Any]) -> None:
    activation_map.parent.mkdir(parents=True, exist_ok=True)
    with activation_map.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")


def _latest(pattern: str) -> Path | None:
    rows = sorted(glob.glob(pattern))
    if not rows:
        return None
    return Path(rows[-1])


def _parse_patch_touched_paths(patch_bytes: bytes) -> list[str]:
    touched: list[str] = []
    seen: set[str] = set()
    for raw in patch_bytes.decode("utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line.startswith("+++ "):
            continue
        if line == "+++ /dev/null":
            continue
        if not line.startswith("+++ b/"):
            continue
        rel = line[len("+++ b/") :]
        rel = rel.split("\t", 1)[0].strip()
        if rel.startswith('\"') and rel.endswith('\"') and len(rel) >= 2:
            rel = rel[1:-1]
        rel = rel.replace("\\\\", "/").lstrip("./")
        if rel and rel not in seen:
            touched.append(rel)
            seen.add(rel)
    return touched


def _find_ccap_bundle_by_hash(state_dir: Path, bundle_hash: str) -> Path | None:
    if not isinstance(bundle_hash, str) or not bundle_hash.startswith("sha256:"):
        return None
    hexd = bundle_hash.split(":", 1)[1]
    if not re.fullmatch(r"[0-9a-f]{64}", hexd or ""):
        return None
    rows = sorted(state_dir.glob(f"subruns/**/promotion/sha256_{hexd}.omega_promotion_bundle_ccap_v1.json"), key=lambda p: p.as_posix())
    if len(rows) == 1:
        return rows[0]
    # fall back to broader search when subruns are pruned/rearranged
    rows = sorted(state_dir.glob(f"subruns/**/sha256_{hexd}.*.json"), key=lambda p: p.as_posix())
    return rows[0] if len(rows) == 1 else None


def _maybe_extract_activation() -> dict[str, Any] | None:
    promo_path = _latest(str(state_dir / "dispatch" / "*" / "promotion" / "sha256_*.omega_promotion_receipt_v1.json"))
    act_path = _latest(str(state_dir / "dispatch" / "*" / "activation" / "sha256_*.omega_activation_receipt_v1.json"))
    if promo_path is None or act_path is None:
        return None
    promo = _load_json(promo_path) or {}
    act = _load_json(act_path) or {}
    if str(((promo.get("result") or {}) if isinstance(promo.get("result"), dict) else {}).get("status", "")).strip() != "PROMOTED":
        return None
    if not bool(act.get("activation_success", False)):
        return None
    bundle_hash = str(promo.get("promotion_bundle_hash", "")).strip()
    bundle_path = _find_ccap_bundle_by_hash(state_dir, bundle_hash)
    if bundle_path is None:
        return None
    bundle = _load_json(bundle_path) or {}
    if str(bundle.get("schema_version", "")).strip() != "omega_promotion_bundle_ccap_v1":
        return None
    patch_rel = str(bundle.get("patch_relpath", "")).strip().replace("\\\\", "/").lstrip("./")
    ccap_id = str(bundle.get("ccap_id", "")).strip()
    activation_key = str(bundle.get("activation_key", "")).strip() or ccap_id
    subrun_root = bundle_path.parent.parent.resolve()
    patch_path = (subrun_root / patch_rel).resolve()
    if not patch_path.exists() or not patch_path.is_file():
        return None
    patch_bytes = patch_path.read_bytes()
    patch_sha256 = "sha256:" + _sha256_hex(patch_bytes)
    touched = _parse_patch_touched_paths(patch_bytes)
    return {
        "bundle_hash": bundle_hash,
        "bundle_path": str(bundle_path),
        "patch_path": str(patch_path),
        "patch_sha256": patch_sha256,
        "touched_paths": touched,
        "activation_key": activation_key,
        "ccap_id": ccap_id,
    }


def _split_csv(value: str) -> set[str]:
    out: set[str] = set()
    for raw in str(value).split(","):
        token = raw.strip()
        if token:
            out.add(token)
    return out


state = _ensure_activation_state()
head_sha = _git(["rev-parse", "HEAD"])

# Stabilize pending after one successful tick runs on the pending git SHA.
pending = state.get("pending")
if isinstance(pending, dict):
    pending_sha = str(pending.get("git_sha", "")).strip()
    if pending_sha and pending_sha == head_sha:
        state["last_stable"] = {
            "activation_key": str(pending.get("activation_key", "")),
            "git_sha": pending_sha,
            "tick_u64": int(tick_u64),
            "ccap_id": pending.get("ccap_id"),
            "bundle_hash": pending.get("bundle_hash"),
            "patch_sha256": pending.get("patch_sha256"),
        }
        state["pending"] = None
        _atomic_write_json(state_path, state)
        _append_map({"ts_utc": _utc_now_iso(), "event": "STABILIZED", "activation_key": state["last_stable"]["activation_key"], "git_sha": pending_sha, "tick_u64": int(tick_u64)})

activation = _maybe_extract_activation()
if activation is None:
    sys.exit(0)

stable_bundle = None
pending_bundle = None
stable = state.get("last_stable")
if isinstance(stable, dict):
    stable_bundle = stable.get("bundle_hash")
pending_now = state.get("pending")
if isinstance(pending_now, dict):
    pending_bundle = pending_now.get("bundle_hash")
if str(activation.get("bundle_hash", "")).strip() and str(activation.get("bundle_hash", "")).strip() in {
    str(stable_bundle or "").strip(),
    str(pending_bundle or "").strip(),
}:
    sys.exit(0)

apply_targets = _split_csv(apply_targets_csv)
touched = [str(p) for p in (activation.get("touched_paths") or [])]
if not touched or any(p not in apply_targets for p in touched):
    receipt = {
        "schema_version": "ignite_patch_landing_receipt_v1",
        "tick_u64": int(tick_u64),
        "decision": "REJECT",
        "reason": "TOUCHED_PATHS_NOT_ALLOWED",
        "bundle_hash": str(activation.get("bundle_hash", "")),
        "ccap_id": str(activation.get("ccap_id", "")),
        "activation_key": str(activation.get("activation_key", "")),
        "patch_sha256": str(activation.get("patch_sha256", "")),
        "touched_paths": touched,
        "apply_targets": sorted(apply_targets),
    }
    sig = _sha256_hex(json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    out_path = landings_dir / f"sha256_{sig}.ignite_patch_landing_receipt_v1.json"
    _atomic_write_json(out_path, receipt)
    sys.exit(0)

patch_path = Path(str(activation["patch_path"]))
patch_sha256 = str(activation["patch_sha256"])
bundle_hash = str(activation["bundle_hash"])
activation_key = str(activation["activation_key"])
ccap_id = str(activation["ccap_id"])

# Apply and commit in the live worktree.
check = subprocess.run(["git", "-C", str(worktree_dir), "apply", "--check", "-p1", str(patch_path)], capture_output=True, text=True)
if check.returncode != 0:
    receipt = {
        "schema_version": "ignite_patch_landing_receipt_v1",
        "tick_u64": int(tick_u64),
        "decision": "REJECT",
        "reason": "GIT_APPLY_CHECK_FAILED",
        "bundle_hash": bundle_hash,
        "ccap_id": ccap_id,
        "activation_key": activation_key,
        "patch_sha256": patch_sha256,
        "touched_paths": touched,
        "stderr": (check.stderr or check.stdout or "").strip()[:4000],
    }
    sig = _sha256_hex(json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    out_path = landings_dir / f"sha256_{sig}.ignite_patch_landing_receipt_v1.json"
    _atomic_write_json(out_path, receipt)
    sys.exit(0)

apply = subprocess.run(["git", "-C", str(worktree_dir), "apply", "-p1", str(patch_path)], capture_output=True, text=True)
if apply.returncode != 0:
    raise RuntimeError((apply.stderr or apply.stdout or "git apply failed").strip())

subprocess.run(["git", "-C", str(worktree_dir), "add", "-A"], check=False)
staged = subprocess.run(["git", "-C", str(worktree_dir), "diff", "--cached", "--quiet"])
if staged.returncode == 0:
    # Nothing staged; treat as no-op landing.
    sys.exit(0)
env = dict(os.environ)
env.setdefault("GIT_AUTHOR_NAME", "omega-ignite")
env.setdefault("GIT_AUTHOR_EMAIL", "omega-ignite@local")
env.setdefault("GIT_COMMITTER_NAME", "omega-ignite")
env.setdefault("GIT_COMMITTER_EMAIL", "omega-ignite@local")
msg = f"CCAP_LAND activation_key={activation_key} ccap_id={ccap_id} bundle_hash={bundle_hash} patch_sha256={patch_sha256}"
commit = subprocess.run(["git", "-C", str(worktree_dir), "commit", "-m", msg], capture_output=True, text=True, env=env)
if commit.returncode != 0:
    # No-op if patch was already applied.
    if "nothing to commit" not in (commit.stderr or commit.stdout or ""):
        raise RuntimeError((commit.stderr or commit.stdout or "git commit failed").strip())

new_head = _git(["rev-parse", "HEAD"])
old_active = active_ptr.read_text(encoding="utf-8").strip() if active_ptr.exists() else ""
_atomic_write_text(prev_ptr, (old_active or "") + "\n")
_atomic_write_text(active_ptr, activation_key + "\n")

state = _ensure_activation_state()
state["pending"] = {
    "activation_key": activation_key,
    "git_sha": new_head,
    "tick_u64": int(tick_u64),
    "ccap_id": ccap_id,
    "bundle_hash": bundle_hash,
    "patch_sha256": patch_sha256,
}
_atomic_write_json(state_path, state)
_append_map({"ts_utc": _utc_now_iso(), "event": "LANDED", "activation_key": activation_key, "git_sha": new_head, "tick_u64": int(tick_u64), "bundle_hash": bundle_hash, "patch_sha256": patch_sha256})

print(
    " ".join(
        [
            "SIGNAL=PATCH_LANDED",
            f"tick={tick_u64}",
            f"activation_key={activation_key}",
            f"git_sha={new_head}",
            "touched=" + ",".join(touched),
        ]
    )
)
PY
}

ignite_on_crash() {
  local tick_u64="$1"
  local exit_code="$2"
  local raw_log="$3"
  python3 - "$tick_u64" "$exit_code" "$OUT_ROOT" "$WORKTREE_DIR" "$raw_log" <<'PY'
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

tick_u64 = int(sys.argv[1])
exit_code = str(sys.argv[2])
out_root = Path(sys.argv[3]).resolve()
worktree_dir = Path(sys.argv[4]).resolve()
raw_log = Path(sys.argv[5]).resolve()

ignite_dir = out_root / "_ignite"
state_path = ignite_dir / "ignite_code_activation_state_v1.json"
active_ptr = ignite_dir / "ACTIVE_CODE_ACTIVATION_KEY"
prev_ptr = ignite_dir / "PREV_ACTIVE_CODE_ACTIVATION_KEY"
activation_map = ignite_dir / "activation_map_v1.jsonl"
deaths_dir = ignite_dir / "deaths"
deaths_dir.mkdir(parents=True, exist_ok=True)


def _utc_now_compact() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    _atomic_write_text(path, text)


state = _load_json(state_path) if state_path.exists() else None
if not isinstance(state, dict) or str(state.get("schema_version", "")) != "ignite_code_activation_state_v1":
    sys.exit(0)

pending = state.get("pending")
last_stable = state.get("last_stable") if isinstance(state.get("last_stable"), dict) else None
if not isinstance(pending, dict) or not isinstance(last_stable, dict):
    sys.exit(0)

rollback_sha = str(last_stable.get("git_sha", "")).strip()
rollback_key = str(last_stable.get("activation_key", "")).strip()
pending_sha = str(pending.get("git_sha", "")).strip()
pending_key = str(pending.get("activation_key", "")).strip()
if not rollback_sha or not rollback_key or not pending_sha or not pending_key:
    sys.exit(0)

raw_bytes = raw_log.read_bytes() if raw_log.exists() else b""
crash_sig = "sha256:" + _sha256_hex(raw_bytes)

subprocess.run(["git", "-C", str(worktree_dir), "reset", "--hard", rollback_sha], check=False)
old_active = active_ptr.read_text(encoding="utf-8").strip() if active_ptr.exists() else ""
_atomic_write_text(prev_ptr, (old_active or "") + "\n")
_atomic_write_text(active_ptr, rollback_key + "\n")

receipt = {
    "schema_version": "omega_death_receipt_v1",
    "tick_u64": int(tick_u64),
    "exit_code": exit_code,
    "crash_signature": crash_sig,
    "raw_log_path": str(raw_log),
    "pending": {"activation_key": pending_key, "git_sha": pending_sha},
    "rollback": {"activation_key": rollback_key, "git_sha": rollback_sha},
}
name = f"{_utc_now_compact()}_sha256_{crash_sig.split(':',1)[1]}.omega_death_receipt_v1.json"
out_path = deaths_dir / name
_atomic_write_json(out_path, receipt)

state["pending"] = None
_atomic_write_json(state_path, state)
activation_map.parent.mkdir(parents=True, exist_ok=True)
with activation_map.open("a", encoding="utf-8") as handle:
    handle.write(
        json.dumps(
            {
                "ts_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "event": "ROLLBACK",
                "tick_u64": int(tick_u64),
                "exit_code": exit_code,
                "crash_signature": crash_sig,
                "pending": {"activation_key": pending_key, "git_sha": pending_sha},
                "rollback": {"activation_key": rollback_key, "git_sha": rollback_sha},
                "death_receipt_rel": out_path.relative_to(out_root).as_posix(),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    )

print(
    " ".join(
        [
            "SIGNAL=ROLLBACK_APPLIED",
            f"tick={tick_u64}",
            f"rollback_activation_key={rollback_key}",
            f"rollback_git_sha={rollback_sha}",
            f"death_receipt_rel={out_path.relative_to(out_root).as_posix()}",
        ]
    )
)
PY
}

timestamp_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log_line() {
  local payload="$1"
  printf '%s %s\n' "$(timestamp_utc)" "$payload" | tee -a "$LOG_PATH"
}

emit_signals_for_tick() {
  local tick_u64="$1"
  local state_dir="$2"
  local raw_log="$3"

  python3 - "$tick_u64" "$state_dir" "$raw_log" <<'PY'
import glob
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

tick_u64 = int(sys.argv[1])
state_dir = Path(sys.argv[2])
raw_log = Path(sys.argv[3])


def latest(pattern: str) -> Path | None:
    rows = sorted(glob.glob(pattern))
    if not rows:
        return None
    return Path(rows[-1])


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def as_token(value: Any) -> str:
    text = str(value)
    if text == "":
        return "NA"
    text = re.sub(r"\s+", "_", text.strip())
    return text if text else "NA"


def hash_from_filename(path: Path | None, suffix: str) -> str:
    if path is None:
        return ""
    name = path.name
    if name.startswith("sha256_") and name.endswith(suffix):
        digest = name[len("sha256_") : -len(suffix)]
        if re.fullmatch(r"[0-9a-f]{64}", digest):
            return f"sha256:{digest}"
    return ""


def emit(signal: str, **fields: Any) -> None:
    parts = [f"SIGNAL={signal}", f"tick={tick_u64}"]
    for key, value in fields.items():
        parts.append(f"{key}={as_token(value)}")
    print(" ".join(parts))


runaway_state = ""
runaway_level = -1
runaway_reason = ""
action_kind_cli = ""
decision_plan_hash_cli = ""
trace_hash_chain_hash_cli = ""
tick_snapshot_hash_cli = ""

if raw_log.exists():
    for raw in raw_log.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("runaway_state:"):
            runaway_state = line.split(":", 1)[1].strip()
        elif line.startswith("runaway_level_u64:"):
            val = line.split(":", 1)[1].strip()
            try:
                runaway_level = int(val)
            except Exception:
                runaway_level = -1
        elif line.startswith("runaway_reason:"):
            runaway_reason = line.split(":", 1)[1].strip()
        elif line.startswith("action_kind:"):
            action_kind_cli = line.split(":", 1)[1].strip()
        elif line.startswith("decision_plan_hash:"):
            decision_plan_hash_cli = line.split(":", 1)[1].strip()
        elif line.startswith("trace_hash_chain_hash:"):
            trace_hash_chain_hash_cli = line.split(":", 1)[1].strip()
        elif line.startswith("tick_snapshot_hash:"):
            tick_snapshot_hash_cli = line.split(":", 1)[1].strip()

decision_path = latest(str(state_dir / "decisions" / "sha256_*.omega_decision_plan_v1.json"))
decision = load_json(decision_path) or {}
decision_plan_hash = decision_plan_hash_cli or hash_from_filename(decision_path, ".omega_decision_plan_v1.json")

tick_outcome_path = latest(str(state_dir / "perf" / "sha256_*.omega_tick_outcome_v1.json"))
tick_outcome = load_json(tick_outcome_path) or {}
trace_hash_chain_hash = trace_hash_chain_hash_cli or str(tick_outcome.get("trace_hash_chain_hash", "")).strip()
tick_snapshot_hash = tick_snapshot_hash_cli or str(tick_outcome.get("tick_snapshot_hash", "")).strip()

promotion_path = latest(str(state_dir / "dispatch" / "*" / "promotion" / "sha256_*.omega_promotion_receipt_v1.json"))
promotion = load_json(promotion_path) or {}
promotion_status = str((promotion.get("result") or {}).get("status", "")).strip()

activation_path = latest(str(state_dir / "dispatch" / "*" / "activation" / "sha256_*.omega_activation_receipt_v1.json"))
activation = load_json(activation_path) or {}
activation_success = bool(activation.get("activation_success", False))

ccap_path = latest(str(state_dir / "dispatch" / "*" / "verifier" / "sha256_*.ccap_receipt_v1.json"))
ccap = load_json(ccap_path) or {}
ccap_decision = str(ccap.get("decision", "")).strip()

rewrite_bundle_paths = sorted(glob.glob(str(state_dir / "subruns" / "*" / "promotion" / "sha256_*.omega_promotion_bundle_ccap_v1.json")))
rewrite_attempt = bool(rewrite_bundle_paths)
rewrite_bundle_rel = ""
if rewrite_bundle_paths:
    try:
        rewrite_bundle_rel = os.path.relpath(rewrite_bundle_paths[-1], state_dir)
    except Exception:
        rewrite_bundle_rel = rewrite_bundle_paths[-1]

selected_metric = str(decision.get("runaway_selected_metric_id", "")).strip()
selected_level = int(decision.get("runaway_escalation_level_u64", -1) or -1)
campaign_id = str(decision.get("campaign_id", "")).strip()
tie_break_path = decision.get("tie_break_path")
if not isinstance(tie_break_path, list):
    tie_break_path = []
tie_break_has_reason = any(str(row).strip() == "RUNAWAY_REASON:TESTING" for row in tie_break_path)

runaway_active = runaway_state == "ACTIVE" and runaway_level == 5 and runaway_reason == "TESTING"
capability_priority = (
    selected_metric == "OBJ_EXPAND_CAPABILITIES"
    and selected_level == 5
    and campaign_id == "rsi_ge_symbiotic_optimizer_sh1_v0_1"
    and tie_break_has_reason
)
rewrite_commit = promotion_status == "PROMOTED"
manifest_changed = bool(tick_outcome.get("manifest_changed", False))
activation_commit = activation_success and manifest_changed

if runaway_active:
    emit("RUNAWAY_ACTIVE", level=runaway_level, reason=runaway_reason)

if capability_priority:
    emit(
        "CAPABILITY_PRIORITY",
        metric=selected_metric,
        campaign=campaign_id,
        level=selected_level,
        reason_trace="RUNAWAY_REASON:TESTING",
    )

if rewrite_attempt:
    emit(
        "REWRITE_ATTEMPT",
        bundle="omega_promotion_bundle_ccap_v1",
        bundle_rel=rewrite_bundle_rel,
    )

if ccap_decision in {"PROMOTE", "REJECT"}:
    emit(
        "CCAP_DECISION",
        decision=ccap_decision,
        ccap_id=str(ccap.get("ccap_id", "")),
    )

if rewrite_commit:
    emit(
        "REWRITE_COMMIT",
        promotion_status=promotion_status,
        receipt=hash_from_filename(promotion_path, ".omega_promotion_receipt_v1.json"),
    )

if activation_commit:
    emit(
        "ACTIVATION_COMMIT",
        activation_success=str(activation_success).lower(),
        manifest_changed=str(manifest_changed).lower(),
        receipt=hash_from_filename(activation_path, ".omega_activation_receipt_v1.json"),
    )

action_kind = str(decision.get("action_kind", "")).strip() or action_kind_cli
emit(
    "HEARTBEAT",
    action_kind=action_kind,
    decision_plan_hash=decision_plan_hash,
    trace_hash_chain_hash=trace_hash_chain_hash,
    tick_snapshot_hash=tick_snapshot_hash,
)

emit(
    "TIER_STATUS",
    tier1=("pass" if (runaway_active and capability_priority) else "fail"),
    tier2=("pass" if rewrite_attempt else "fail"),
    tier3=("pass" if (rewrite_commit and activation_commit) else "fail"),
    selected_metric=selected_metric,
    promotion_status=(promotion_status or "NONE"),
    activation_success=str(activation_success).lower(),
    manifest_changed=str(manifest_changed).lower(),
)
PY
}

tick_u64="$START_TICK"
prev_state_dir=""
consecutive_crash_count=0
attempt_u64=0

log_line "SIGNAL=IGNITE_START tick=${tick_u64} profile=rsi_omega_daemon_v19_0_super_unified campaign_pack=${CAMPAIGN_PACK}"

trap 'log_line "SIGNAL=IGNITE_STOP tick=${tick_u64} reason=INTERRUPTED"; exit 0' INT TERM

while :; do
  tick_id="$(printf '%04d' "$tick_u64")"
  out_dir="${OUT_ROOT}_tick_${tick_id}"

  attempt_u64=$((attempt_u64 + 1))
  attempt_id="$(printf '%04d' "$attempt_u64")"
  raw_log="${RAW_ROOT}/tick_${tick_id}_attempt_${attempt_id}.log"
  rm -rf "$out_dir"

  cmd=(
    python3 -m orchestrator.rsi_omega_daemon_v19_0
    --campaign_pack "$CAMPAIGN_PACK"
    --out_dir "$out_dir"
    --mode once
    --tick_u64 "$tick_u64"
  )
  if [[ -n "$prev_state_dir" ]]; then
    cmd+=(--prev_state_dir "$prev_state_dir")
  fi

	  (
	    cd "$WORKTREE_DIR" || exit 1
	    env \
	      PYTHONPATH=".:CDEL-v2:${ROOT}/agi-orchestrator${PYTHONPATH:+:${PYTHONPATH}}" \
	      OMEGA_HOST_REPO_ROOT="$ROOT" \
	      OMEGA_PHASE3_MUTATION_SIGNAL="${OMEGA_PHASE3_MUTATION_SIGNAL:-1}" \
	      OMEGA_META_CORE_ACTIVATION_MODE="$ACTIVATION_MODE" \
	      OMEGA_ALLOW_SIMULATE_ACTIVATION="$ALLOW_SIMULATE" \
	      "${cmd[@]}"
	  ) >"$raw_log" 2>&1
	  run_status="$?"

	  if [[ "$run_status" == "0" ]]; then
	    state_dir="${out_dir}/daemon/rsi_omega_daemon_v19_0/state"
	    if [[ ! -d "$state_dir" ]]; then
	      consecutive_crash_count=$((consecutive_crash_count + 1))
	      ignite_on_crash "$tick_u64" "MISSING_STATE_DIR" "$raw_log" | while IFS= read -r row; do log_line "$row"; done
	      log_line \
	        "SIGNAL=RESURRECT tick=${tick_u64} exit_code=MISSING_STATE_DIR consecutive_crash_count=${consecutive_crash_count} raw_log=${raw_log}"
	      sleep "$SLEEP_SECONDS"
	      continue
	    fi

	    ignite_on_success "$tick_u64" "$state_dir" "$raw_log" | while IFS= read -r row; do log_line "$row"; done
	    while IFS= read -r row; do
	      [[ -n "$row" ]] || continue
	      log_line "$row"
	    done < <(emit_signals_for_tick "$tick_u64" "$state_dir" "$raw_log")

	    prev_state_dir="$state_dir"
	    tick_u64=$((tick_u64 + 1))
	    consecutive_crash_count=0
	    attempt_u64=0
	    continue
	  fi

	  exit_code="$run_status"
	  consecutive_crash_count=$((consecutive_crash_count + 1))
	  ignite_on_crash "$tick_u64" "$exit_code" "$raw_log" | while IFS= read -r row; do log_line "$row"; done
	  log_line \
	    "SIGNAL=RESURRECT tick=${tick_u64} exit_code=${exit_code} consecutive_crash_count=${consecutive_crash_count} raw_log=${raw_log}"
	  sleep "$SLEEP_SECONDS"
	done
