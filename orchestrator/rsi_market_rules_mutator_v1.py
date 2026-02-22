"""Phase 3 CCAP market-rules self-mutation campaign (v1).

Targets `orchestrator/omega_bid_market_v1.py` and requires determinism/soak + v19 replay VALID
before emitting a CCAP bundle.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins
from cdel.v18_0.ccap_runtime_v1 import ccap_payload_id, compute_repo_base_tree_id_tolerant
from cdel.v18_0.omega_common_v1 import canon_hash_obj, fail, load_canon_dict, require_no_absolute_paths
from orchestrator.llm_backend import get_backend

_PACK_SCHEMA = "rsi_market_rules_mutator_pack_v1"
_BENCH_PACK_DEFAULT = "campaigns/rsi_omega_daemon_v19_0_phase3_market_toy/rsi_omega_daemon_pack_v1.json"
_LOCKED_TARGET_RELPATH = "orchestrator/omega_bid_market_v1.py"


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _diff_from_updated_text(*, target_relpath: str, before: str, after: str) -> str:
    rows = difflib.unified_diff(
        before.splitlines(True),
        after.splitlines(True),
        fromfile=f"a/{target_relpath}",
        tofile=f"b/{target_relpath}",
    )
    patch_text = "".join(rows)
    if not patch_text.endswith("\n"):
        patch_text += "\n"
    return patch_text


def _template_patch_for_target(*, target_relpath: str, target_text: str, tick_u64: int) -> str:
    before = str(target_text)
    after = before

    bankruptcy_old = (
        "    disabled_b = bool(campaign_state.get(\"disabled_b\", False))\n"
        "    if disabled_b:\n"
        "        return (\n"
        "            max(0, int(campaign_state.get(\"bankruptcy_streak_u64\", 0))),\n"
        "            True,\n"
        "            str(campaign_state.get(\"disabled_reason\", \"\") or \"N/A\"),\n"
        "            int(bankroll_q32),\n"
        "        )\n"
    )
    bankruptcy_new = (
        "    disabled_b = bool(campaign_state.get(\"disabled_b\", False))\n"
        "    if disabled_b:\n"
        "        recovered_bankroll_q32 = int(bankroll_q32) + max(1, int(disable_threshold_q32) // 2)\n"
        "        if recovered_bankroll_q32 >= int(disable_threshold_q32):\n"
        "            return 0, False, \"RECOVERED\", int(recovered_bankroll_q32)\n"
        "        return (\n"
        "            max(0, int(campaign_state.get(\"bankruptcy_streak_u64\", 0))),\n"
        "            True,\n"
        "            str(campaign_state.get(\"disabled_reason\", \"\") or \"N/A\"),\n"
        "            int(recovered_bankroll_q32),\n"
        "        )\n"
    )
    if bankruptcy_old in after:
        after = after.replace(bankruptcy_old, bankruptcy_new, 1)

    score_old = (
        "        roi_q32 = int((int(pred_delta) << 32) // max(1, int(pred_cost)))\n"
        "        confidence_penalty_q32 = int(confidence_q32)\n"
        "        score_q32 = int(\n"
        "            q32_mul(\n"
        "                int(q32_mul(int(roi_q32), int(credibility_q32))),\n"
        "                int(confidence_penalty_q32),\n"
        "            )\n"
        "        )\n"
    )
    score_new = (
        "        roi_q32 = int((int(pred_delta) << 32) // max(1, int(pred_cost)))\n"
        "        confidence_penalty_q32 = max(1, int(Q32_ONE - int(confidence_q32)))\n"
        "        score_q32 = int(\n"
        "            q32_mul(\n"
        "                int(q32_mul(int(roi_q32), int(credibility_q32))),\n"
        "                int(confidence_penalty_q32),\n"
        "            )\n"
        "        )\n"
    )
    if score_old in after:
        after = after.replace(score_old, score_new, 1)

    eligibility_old = (
        "        cooldown_next = int(((cooldowns.get(campaign_id) or {}).get(\"next_tick_allowed_u64\", 0)))\n"
        "        if bool(cstate.get(\"disabled_b\", False)):\n"
        "            eligible_b = False\n"
        "            skip_reason = \"DISABLED\"\n"
        "        elif cooldown_next > int(tick_u64):\n"
    )
    eligibility_new = (
        "        cooldown_next = int(((cooldowns.get(campaign_id) or {}).get(\"next_tick_allowed_u64\", 0)))\n"
        "        disabled_recovery_b = bool(cstate.get(\"disabled_b\", False)) and int(max(0, q32_int(cstate.get(\"bankroll_q32\")))) >= int(pred_cost)\n"
        "        if bool(cstate.get(\"disabled_b\", False)) and not disabled_recovery_b:\n"
        "            eligible_b = False\n"
        "            skip_reason = \"DISABLED\"\n"
        "        elif cooldown_next > int(tick_u64):\n"
    )
    if eligibility_old in after:
        after = after.replace(eligibility_old, eligibility_new, 1)

    tie_break_old = (
        "    tie_break_path = [\n"
        "        \"MARKET_RANK:score_q32_desc\",\n"
        "        \"MARKET_RANK:roi_q32_desc\",\n"
        "        \"MARKET_RANK:credibility_q32_desc\",\n"
        "        \"MARKET_RANK:confidence_q32_desc\",\n"
        "        \"MARKET_RANK:campaign_id_asc\",\n"
    )
    tie_break_new = (
        "    tie_break_path = [\n"
        "        \"MARKET_SCORING_MODE:CONFIDENCE_PENALTY_V2\",\n"
        "        \"MARKET_ELIGIBILITY_GATE:DISABLED_RECOVERY_V1\",\n"
        "        \"MARKET_RANK:score_q32_desc\",\n"
        "        \"MARKET_RANK:roi_q32_desc\",\n"
        "        \"MARKET_RANK:credibility_q32_desc\",\n"
        "        \"MARKET_RANK:confidence_q32_desc\",\n"
        "        \"MARKET_RANK:campaign_id_asc\",\n"
    )
    if tie_break_old in after:
        after = after.replace(tie_break_old, tie_break_new, 1)

    if after == before:
        raise RuntimeError(f"TEMPLATE_PATCH_NOOP:{int(tick_u64)}")
    return _diff_from_updated_text(target_relpath=target_relpath, before=before, after=after)


def _extract_json_obj(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise RuntimeError("NO_LLM_RESPONSE")
    candidates: list[str] = [raw]
    if "```" in raw:
        for fence in ("```json", "```"):
            start = raw.find(fence)
            if start >= 0:
                end = raw.find("```", start + len(fence))
                if end > start:
                    candidates.insert(0, raw[start + len(fence) : end].strip())
    if "{" in raw and "}" in raw:
        candidates.append(raw[raw.find("{") : raw.rfind("}") + 1].strip())
    last_err: Exception | None = None
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
        if isinstance(obj, dict):
            return obj
    # Best-effort extraction for invalid JSON-with-newlines responses.
    def _extract_loose_json_string_field(src: str, field: str) -> str | None:
        needle = f"\"{field}\""
        idx = src.find(needle)
        if idx < 0:
            return None
        colon = src.find(":", idx + len(needle))
        if colon < 0:
            return None
        k = colon + 1
        while k < len(src) and src[k].isspace():
            k += 1
        if k >= len(src) or src[k] != "\"":
            return None
        k += 1
        raw_chars: list[str] = []
        escaped = False
        while k < len(src):
            ch = src[k]
            if escaped:
                raw_chars.append(ch)
                escaped = False
            else:
                if ch == "\\":
                    raw_chars.append(ch)
                    escaped = True
                elif ch == "\"":
                    break
                else:
                    raw_chars.append(ch)
            k += 1
        raw_val = "".join(raw_chars)
        cooked = raw_val.replace("\r", "\\r").replace("\n", "\\n")
        try:
            return json.loads("\"" + cooked + "\"")
        except Exception:  # noqa: BLE001
            return (
                cooked.replace("\\n", "\n")
                .replace("\\r", "\r")
                .replace("\\t", "\t")
                .replace("\\\"", "\"")
                .replace("\\\\", "\\")
            )

    updated = _extract_loose_json_string_field(raw, "updated_file_text")
    unified = _extract_loose_json_string_field(raw, "unified_diff")
    if isinstance(updated, str) and updated.strip():
        return {"updated_file_text": updated}
    if isinstance(unified, str) and unified.strip():
        return {"unified_diff": unified}
    raise RuntimeError("LLM_RESPONSE_NOT_JSON") from last_err


def _extract_unified_diff_text(text: str) -> str | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    # If the model tried to return JSON but made it invalid, try to extract the unified_diff value anyway.
    if "\"unified_diff\"" in raw:
        try:
            obj = _extract_json_obj(raw)
            if isinstance(obj.get("unified_diff"), str) and str(obj["unified_diff"]).strip():
                patch = str(obj["unified_diff"])
                return patch if patch.endswith("\n") else patch + "\n"
        except Exception:
            pass
    candidates: list[str] = [raw]
    if "```" in raw:
        for fence in ("```diff", "```patch", "```json", "```"):
            start = raw.find(fence)
            if start >= 0:
                end = raw.find("```", start + len(fence))
                if end > start:
                    candidates.insert(0, raw[start + len(fence) : end].strip())
    for cand in candidates:
        if "+++ b/" in cand and ("--- a/" in cand or "diff --git " in cand):
            lines = cand.splitlines()
            start = 0
            for idx, line in enumerate(lines):
                if line.startswith("diff --git ") or line.startswith("--- a/"):
                    start = idx
                    break
            return "\n".join(lines[start:]).strip() + "\n"
    return None


def _ensure_patch_headers(patch_text: str, *, target_relpath: str) -> str:
    text = str(patch_text or "")
    if ("--- " not in text and "+++ " not in text) and "@@" in text:
        header = f"--- a/{target_relpath}\n+++ b/{target_relpath}\n"
        text = header + text.lstrip("\n")
    lines = text.splitlines()
    saw_minus = False
    saw_plus = False
    for idx, line in enumerate(lines):
        if line.startswith("--- ") and line != "--- /dev/null" and not saw_minus:
            if not line.startswith("--- a/"):
                lines[idx] = f"--- a/{target_relpath}"
            saw_minus = True
        elif line.startswith("+++ ") and line != "+++ /dev/null" and not saw_plus:
            if not line.startswith("+++ b/"):
                lines[idx] = f"+++ b/{target_relpath}"
            saw_plus = True
        if saw_minus and saw_plus:
            break
    # Repair common LLM hunk formatting bug: context lines inside hunks missing
    # the required leading space prefix.
    repaired_lines: list[str] = []
    in_hunk = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("@@ "):
            in_hunk = True
            repaired_lines.append(stripped)
            continue
        if stripped.startswith("diff --git ") or stripped.startswith("--- ") or stripped.startswith("+++ "):
            in_hunk = False
            repaired_lines.append(stripped)
            continue
        if in_hunk and not (
            line.startswith(" ")
            or line.startswith("+")
            or line.startswith("-")
            or line.startswith("\\ No newline at end of file")
        ):
            repaired_lines.append(" " + line)
            continue
        repaired_lines.append(line)

    text = "\n".join(repaired_lines) + ("\n" if text.endswith("\n") else "")
    if not text.endswith("\n"):
        text += "\n"
    return text

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
        if rel.startswith('"') and rel.endswith('"') and len(rel) >= 2:
            rel = rel[1:-1]
        rel = rel.replace("\\", "/").lstrip("./")
        if rel and rel not in seen:
            touched.append(rel)
            seen.add(rel)
    return touched


def _repair_patch_prefix_that_applies(*, worktree: Path, patch_bytes: bytes) -> bytes | None:
    """Best-effort salvage for truncated LLM patches by trimming trailing lines."""
    def _check(candidate_bytes: bytes, *, tolerant_b: bool) -> bool:
        tmp_path = worktree / ".omega_patch_repair_tmp.patch"
        tmp_path.write_bytes(candidate_bytes)
        try:
            args = ["apply", "--check", "-p1", str(tmp_path)]
            if tolerant_b:
                args = ["apply", "--check", "--recount", "--ignore-whitespace", "-p1", str(tmp_path)]
            _git(worktree, args)
            return True
        except Exception:
            return False

    lines = patch_bytes.decode("utf-8", errors="replace").splitlines()
    if not lines:
        return None
    max_trim = min(len(lines) - 1, 4096)
    for trim_u64 in range(1, max_trim + 1):
        candidate_lines = lines[:-trim_u64]
        if len(candidate_lines) < 4:
            break
        candidate_text = "\n".join(candidate_lines).rstrip("\n") + "\n"
        candidate_bytes = candidate_text.encode("utf-8")
        if _check(candidate_bytes, tolerant_b=False) or _check(candidate_bytes, tolerant_b=True):
            return candidate_bytes

    header_lines: list[str] = []
    hunk_blocks: list[list[str]] = []
    current_hunk: list[str] | None = None
    saw_hunk = False
    for line in lines:
        if line.startswith("@@ "):
            saw_hunk = True
            if current_hunk is not None:
                hunk_blocks.append(current_hunk)
            current_hunk = [line]
            continue
        if not saw_hunk:
            header_lines.append(line)
            continue
        if current_hunk is None:
            current_hunk = []
        current_hunk.append(line)
    if current_hunk is not None:
        hunk_blocks.append(current_hunk)

    for hunk in hunk_blocks:
        if not hunk:
            continue
        candidate_text = "\n".join([*header_lines, *hunk]).rstrip("\n") + "\n"
        candidate_bytes = candidate_text.encode("utf-8")
        if _check(candidate_bytes, tolerant_b=True):
            return candidate_bytes
    return None


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    return float(statistics.median(xs))


def _fmt_f64(value: float) -> str:
    return format(float(value), ".12f")


def _latest_glob(root: Path, pattern: str) -> Path:
    rows = sorted(root.glob(pattern), key=lambda p: p.as_posix())
    if not rows:
        raise RuntimeError("MISSING_STATE_INPUT")
    return rows[-1]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _git(repo_root: Path, args: list[str]) -> None:
    run = subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=False)
    if run.returncode != 0:
        msg = (run.stderr or run.stdout or "").strip()
        raise RuntimeError(msg or "git failed")


def _git_out(repo_root: Path, args: list[str]) -> str:
    run = subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=False)
    if run.returncode != 0:
        msg = (run.stderr or run.stdout or "").strip()
        raise RuntimeError(msg or "git failed")
    return (run.stdout or "").strip()


def _git_out_bytes(repo_root: Path, args: list[str]) -> bytes:
    run = subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=False, check=False)
    if run.returncode != 0:
        stderr = (run.stderr or b"").decode("utf-8", errors="replace").strip()
        stdout = (run.stdout or b"").decode("utf-8", errors="replace").strip()
        msg = stderr or stdout
        raise RuntimeError(msg or "git failed")
    return bytes(run.stdout or b"")


class _StripLiteralValues(ast.NodeTransformer):
    def visit_Constant(self, node: ast.Constant) -> ast.AST:  # noqa: N802
        value = node.value
        if isinstance(value, bool):
            replacement: Any = False
        elif isinstance(value, (int, float, complex)):
            replacement = 0
        elif isinstance(value, str):
            replacement = ""
        elif isinstance(value, bytes):
            replacement = b""
        elif value is None:
            replacement = None
        else:
            replacement = None
        return ast.copy_location(ast.Constant(value=replacement), node)


def _ast_signature(text: str, *, strip_literals: bool) -> str | None:
    try:
        tree = ast.parse(text)
    except Exception:
        return None
    if strip_literals:
        tree = _StripLiteralValues().visit(tree)  # type: ignore[assignment]
        ast.fix_missing_locations(tree)
    return ast.dump(tree, include_attributes=False)


def _patch_nontrivial_reason(*, before_text: str, after_text: str, patch_bytes: bytes) -> str | None:
    meaningful_lines: list[str] = []
    for row in patch_bytes.decode("utf-8", errors="replace").splitlines():
        if row.startswith(("diff --git ", "index ", "--- ", "+++ ", "@@ ")):
            continue
        if not row or row[0] not in {"+", "-"}:
            continue
        stripped = row[1:].strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        meaningful_lines.append(stripped)
    if not meaningful_lines:
        return "TRIVIAL_PATCH"

    sig_before = _ast_signature(before_text, strip_literals=False)
    sig_after = _ast_signature(after_text, strip_literals=False)
    if sig_before is not None and sig_after is not None and sig_before == sig_after:
        return "TRIVIAL_PATCH"

    sig_before_no_literals = _ast_signature(before_text, strip_literals=True)
    sig_after_no_literals = _ast_signature(after_text, strip_literals=True)
    if (
        sig_before_no_literals is not None
        and sig_after_no_literals is not None
        and sig_before_no_literals == sig_after_no_literals
    ):
        return "CONSTANTS_ONLY_PATCH"
    return None


def _python_gate_env() -> dict[str, str]:
    env = dict(os.environ)
    host_root = str(env.get("OMEGA_HOST_REPO_ROOT", "") or "").strip()
    host_ext = str(Path(host_root) / "agi-orchestrator") if host_root else "agi-orchestrator"
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") or f".:CDEL-v2:{host_ext}"
    return env


def _run_python_gate(*, repo_root: Path, args: list[str]) -> None:
    run = subprocess.run(
        [sys.executable, *args],
        cwd=str(repo_root),
        env=_python_gate_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0:
        detail = (run.stderr or run.stdout or "").strip()
        raise RuntimeError(detail[:4000] or "PYTHON_GATE_FAILED")


def _run_v19_replay_verdict(*, repo_root: Path, state_dir: Path) -> str:
    env = dict(os.environ)
    host_root = str(env.get("OMEGA_HOST_REPO_ROOT", "") or "").strip()
    host_ext = str(Path(host_root) / "agi-orchestrator") if host_root else "agi-orchestrator"
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") or f".:CDEL-v2:{host_ext}"
    cmd = [
        sys.executable,
        "-m",
        "cdel.v19_0.verify_rsi_omega_daemon_v1",
        "--state_dir",
        str(state_dir),
        "--mode",
        "full",
    ]
    run = subprocess.run(
        cmd,
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = str(run.stdout or "").strip()
    stderr = str(run.stderr or "").strip()
    if run.returncode == 0 and stdout == "VALID":
        return "VALID"
    detail = stdout or stderr or "INVALID:VERIFY_ERROR"
    if detail.startswith("INVALID:"):
        return detail
    return f"INVALID:{detail[:3900]}"


def _winner_sequence_from_state(state_dir: Path) -> list[dict[str, Any]]:
    selection_dirs: list[Path] = []
    direct_selection_dir = state_dir / "market" / "selection"
    if direct_selection_dir.is_dir():
        selection_dirs.append(direct_selection_dir)

    # For bench trials, include every tick_* state so divergence is measured across
    # the full selection trajectory, not only the final tick snapshot.
    try:
        trial_root = state_dir.resolve().parents[3]
        if trial_root.name in {"baseline", "candidate"}:
            trial_selection_dirs: list[Path] = []
            for tick_dir in sorted(trial_root.glob("tick_*"), key=lambda p: p.as_posix()):
                sel = tick_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state" / "market" / "selection"
                if sel.is_dir():
                    trial_selection_dirs.append(sel)
            if trial_selection_dirs:
                selection_dirs = trial_selection_dirs
    except Exception:
        pass

    if not selection_dirs:
        return []

    winner_by_tick: dict[int, str] = {}
    for selection_dir in selection_dirs:
        for path in sorted(selection_dir.glob("sha256_*.bid_selection_receipt_v1.json"), key=lambda p: p.as_posix()):
            payload = _load_json(path)
            if str(payload.get("schema_version", "")).strip() != "bid_selection_receipt_v1":
                continue
            if str(payload.get("outcome", "")).strip() != "OK":
                continue
            winner = payload.get("winner")
            if not isinstance(winner, dict):
                continue
            campaign_id = str(winner.get("campaign_id", "")).strip()
            if not campaign_id:
                continue
            tick_u64 = int(payload.get("tick_u64", 0))
            winner_by_tick[tick_u64] = campaign_id

    return [
        {"tick_u64": int(tick_u64), "campaign_id": str(winner_by_tick[tick_u64])}
        for tick_u64 in sorted(winner_by_tick.keys())
    ]


def _winner_dynamics_trial_delta(
    *,
    baseline_seq: list[dict[str, Any]],
    candidate_seq: list[dict[str, Any]],
) -> dict[str, Any]:
    max_len = max(len(baseline_seq), len(candidate_seq))
    first_delta: dict[str, Any] | None = None
    for idx in range(max_len):
        base_row = baseline_seq[idx] if idx < len(baseline_seq) else None
        cand_row = candidate_seq[idx] if idx < len(candidate_seq) else None
        if base_row == cand_row:
            continue
        first_delta = {
            "index_u64": int(idx),
            "tick_u64_baseline": int((base_row or {}).get("tick_u64", -1)),
            "tick_u64_candidate": int((cand_row or {}).get("tick_u64", -1)),
            "campaign_id_baseline": str((base_row or {}).get("campaign_id", "")),
            "campaign_id_candidate": str((cand_row or {}).get("campaign_id", "")),
        }
        break
    return {
        "changed_b": bool(first_delta is not None),
        "first_delta": first_delta,
    }


def _canonical_patch_from_worktree(*, worktree: Path, target_relpath: str) -> bytes:
    patch_bytes = _git_out_bytes(
        worktree,
        ["-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff", "--binary", "--", str(target_relpath)],
    )
    if not patch_bytes:
        raise RuntimeError("EMPTY_PATCH_AFTER_APPLY")
    if not patch_bytes.endswith(b"\n"):
        patch_bytes += b"\n"
    return patch_bytes


def _first_build_recipe_id(repo_root: Path) -> str:
    payload = load_canon_dict(repo_root / "authority" / "build_recipes" / "build_recipes_v1.json", reason="MISSING_STATE_INPUT")
    recipes = payload.get("recipes")
    if payload.get("schema_version") != "build_recipes_v1" or not isinstance(recipes, list) or not recipes:
        fail("SCHEMA_FAIL")
    ids = sorted(str(row.get("recipe_id", "")).strip() for row in recipes if isinstance(row, dict))
    ids = [row for row in ids if row.startswith("sha256:")]
    if not ids:
        fail("SCHEMA_FAIL")
    return ids[0]


def _run_daemon_loop(
    *,
    repo_root: Path,
    campaign_pack_rel: str,
    out_root: Path,
    tick_start_u64: int,
    ticks_u64: int,
    run_seed_u64: int,
    deterministic_timing: bool,
) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    out_pattern = str((out_root / "tick_{tick}").resolve())
    env = dict(os.environ)
    env["OMEGA_RUN_SEED_U64"] = str(int(run_seed_u64))
    env["OMEGA_V19_DETERMINISTIC_TIMING"] = ("1" if deterministic_timing else "0")
    env["OMEGA_PHASE3_MUTATION_SIGNAL"] = "0"
    env["OMEGA_DEV_DEATH_INJECTION_OK"] = "0"
    host_root = str(env.get("OMEGA_HOST_REPO_ROOT", "") or "").strip()
    host_ext = str(Path(host_root) / "agi-orchestrator") if host_root else "agi-orchestrator"
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") or f".:CDEL-v2:{host_ext}"
    cmd = [
        sys.executable,
        "-m",
        "orchestrator.rsi_omega_daemon_v19_0",
        "--campaign_pack",
        str(campaign_pack_rel),
        "--out_dir",
        out_pattern,
        "--mode",
        "loop",
        "--tick_u64",
        str(int(tick_start_u64)),
        "--ticks",
        str(int(ticks_u64)),
    ]
    run = subprocess.run(cmd, cwd=str(repo_root), env=env, capture_output=True, text=True, check=False)
    if run.returncode != 0:
        detail = (run.stderr or run.stdout or "").strip()
        raise RuntimeError(f"DAEMON_RUN_FAILED:{detail[:4000]}")
    last_tick = int(tick_start_u64) + int(ticks_u64) - 1
    last_out = out_root / f"tick_{last_tick}"
    state_dir = last_out / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    if not state_dir.is_dir():
        raise RuntimeError("MISSING_STATE_INPUT")
    return state_dir


def _run_daemon_loop_measured(
    *,
    repo_root: Path,
    campaign_pack_rel: str,
    out_root: Path,
    tick_start_u64: int,
    ticks_u64: int,
    run_seed_u64: int,
    deterministic_timing: bool,
    sample_period_s: float = 0.25,
) -> tuple[Path, dict[str, Any]]:
    out_root.mkdir(parents=True, exist_ok=True)
    out_pattern = str((out_root / "tick_{tick}").resolve())
    env = dict(os.environ)
    env["OMEGA_RUN_SEED_U64"] = str(int(run_seed_u64))
    env["OMEGA_V19_DETERMINISTIC_TIMING"] = ("1" if deterministic_timing else "0")
    env["OMEGA_PHASE3_MUTATION_SIGNAL"] = "0"
    env["OMEGA_DEV_DEATH_INJECTION_OK"] = "0"
    host_root = str(env.get("OMEGA_HOST_REPO_ROOT", "") or "").strip()
    host_ext = str(Path(host_root) / "agi-orchestrator") if host_root else "agi-orchestrator"
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") or f".:CDEL-v2:{host_ext}"
    cmd = [
        sys.executable,
        "-m",
        "orchestrator.rsi_omega_daemon_v19_0",
        "--campaign_pack",
        str(campaign_pack_rel),
        "--out_dir",
        out_pattern,
        "--mode",
        "loop",
        "--tick_u64",
        str(int(tick_start_u64)),
        "--ticks",
        str(int(ticks_u64)),
    ]

    stdout_path = out_root / "stdout.log"
    stderr_path = out_root / "stderr.log"

    def _rss_kb(pid: int) -> int | None:
        run = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, check=False)
        if run.returncode != 0:
            return None
        try:
            return int(str(run.stdout or "").strip().split()[0])
        except Exception:
            return None

    def _fd_count(pid: int) -> int | None:
        if subprocess.run(["command", "-v", "lsof"], capture_output=True, text=True).returncode != 0:
            return None
        run = subprocess.run(["lsof", "-p", str(pid)], capture_output=True, text=True, check=False)
        if run.returncode != 0:
            return None
        lines = (run.stdout or "").splitlines()
        return max(0, len(lines) - 1) if lines else 0

    with stdout_path.open("w", encoding="utf-8") as out_h, stderr_path.open("w", encoding="utf-8") as err_h:
        proc = subprocess.Popen(cmd, cwd=str(repo_root), env=env, stdout=out_h, stderr=err_h)
        pid = int(proc.pid)
        rss_start = _rss_kb(pid)
        fd_start = _fd_count(pid)
        rss_max = rss_start
        fd_max = fd_start
        while True:
            rc = proc.poll()
            if rc is not None:
                break
            rss_now = _rss_kb(pid)
            fd_now = _fd_count(pid)
            if rss_now is not None:
                rss_max = rss_now if rss_max is None else max(rss_max, rss_now)
            if fd_now is not None:
                fd_max = fd_now if fd_max is None else max(fd_max, fd_now)
            time.sleep(max(0.05, float(sample_period_s)))
        rc = int(proc.returncode or 0)

    if rc != 0:
        raise RuntimeError("DAEMON_RUN_FAILED")

    last_tick = int(tick_start_u64) + int(ticks_u64) - 1
    last_out = out_root / f"tick_{last_tick}"
    state_dir = last_out / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    if not state_dir.is_dir():
        raise RuntimeError("MISSING_STATE_INPUT")

    rss_delta_bytes = None
    if rss_start is not None and rss_max is not None:
        rss_delta_bytes = max(0, int(rss_max - rss_start)) * 1024
    fd_delta = None
    if fd_start is not None and fd_max is not None:
        fd_delta = max(0, int(fd_max - fd_start))
    return state_dir, {
        "return_code": rc,
        "rss_start_kb": rss_start,
        "rss_max_kb": rss_max,
        "rss_delta_bytes_u64": rss_delta_bytes,
        "fd_start_u64": fd_start,
        "fd_max_u64": fd_max,
        "fd_delta_u64": fd_delta,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def _score_metric_q32(state_dir: Path, *, metric: str) -> int:
    if metric != "median_stps_non_noop_q32":
        raise RuntimeError("SCHEMA_FAIL")
    score_path = _latest_glob(state_dir / "perf", "sha256_*.omega_run_scorecard_v1.json")
    score = _load_json(score_path)
    return max(0, int(score.get("median_stps_non_noop_q32", 0)))


def _micro_bench_gate(
    *,
    baseline_worktree: Path,
    candidate_worktree: Path,
    bench_pack_rel: str,
    seed_u64: int,
    deterministic_timing_b: bool,
    out_dir: Path,
    wall_ms_max_u64: int,
) -> dict[str, Any]:
    started_ns = time.monotonic_ns()
    baseline_state_dir = _run_daemon_loop(
        repo_root=baseline_worktree,
        campaign_pack_rel=bench_pack_rel,
        out_root=out_dir / "micro_bench" / "baseline",
        tick_start_u64=1,
        ticks_u64=2,
        run_seed_u64=int(seed_u64),
        deterministic_timing=bool(deterministic_timing_b),
    )
    candidate_state_dir = _run_daemon_loop(
        repo_root=candidate_worktree,
        campaign_pack_rel=bench_pack_rel,
        out_root=out_dir / "micro_bench" / "candidate",
        tick_start_u64=1,
        ticks_u64=2,
        run_seed_u64=int(seed_u64),
        deterministic_timing=bool(deterministic_timing_b),
    )
    baseline_verdict = _run_v19_replay_verdict(repo_root=baseline_worktree, state_dir=baseline_state_dir)
    candidate_verdict = _run_v19_replay_verdict(repo_root=candidate_worktree, state_dir=candidate_state_dir)
    if baseline_verdict != "VALID" or candidate_verdict != "VALID":
        raise RuntimeError(f"MICRO_BENCH_REPLAY_INVALID:{baseline_verdict}:{candidate_verdict}")
    elapsed_ms = int((time.monotonic_ns() - started_ns) // 1_000_000)
    if int(wall_ms_max_u64) > 0 and elapsed_ms > int(wall_ms_max_u64):
        raise RuntimeError("MICRO_BENCH_WALL_CAP_EXCEEDED")
    return {
        "schema_version": "market_rules_mutator_micro_bench_receipt_v1",
        "ticks_u64": 2,
        "seed_u64": int(seed_u64),
        "deterministic_timing_b": bool(deterministic_timing_b),
        "elapsed_ms_u64": int(elapsed_ms),
        "wall_ms_max_u64": int(wall_ms_max_u64),
        "baseline_state_dir": str(baseline_state_dir),
        "candidate_state_dir": str(candidate_state_dir),
        "baseline_verdict": baseline_verdict,
        "candidate_verdict": candidate_verdict,
    }


def _disk_usage_mb(root: Path) -> int:
    total = 0
    for path in [root, *sorted(root.rglob("*"))]:
        if path.is_symlink():
            continue
        if path.is_file():
            try:
                total += int(path.stat().st_size)
            except OSError:
                continue
    return int((total + (1024 * 1024) - 1) // (1024 * 1024))


def _structural_validate(
    *,
    candidate_worktree: Path,
    bench_pack_rel: str,
    soak_ticks_u64: int,
    seed_u64: int,
    max_disk_mb_u64: int,
    max_fd_delta_u64: int,
    max_rss_delta_bytes_u64: int,
    require_tree_hash_match_b: bool,
    out_dir: Path,
) -> tuple[dict[str, Any], Path]:
    from cdel.v18_0.omega_common_v1 import tree_hash

    run_root = out_dir / "structural"
    run_a, meas_a = _run_daemon_loop_measured(
        repo_root=candidate_worktree,
        campaign_pack_rel=bench_pack_rel,
        out_root=run_root / "run_a",
        tick_start_u64=1,
        ticks_u64=soak_ticks_u64,
        run_seed_u64=seed_u64,
        deterministic_timing=True,
    )
    run_b, meas_b = _run_daemon_loop_measured(
        repo_root=candidate_worktree,
        campaign_pack_rel=bench_pack_rel,
        out_root=run_root / "run_b",
        tick_start_u64=1,
        ticks_u64=soak_ticks_u64,
        run_seed_u64=seed_u64,
        deterministic_timing=True,
    )
    hash_a = tree_hash(run_a)
    hash_b = tree_hash(run_b)
    disk_a = _disk_usage_mb(run_a)
    disk_b = _disk_usage_mb(run_b)
    if disk_a > int(max_disk_mb_u64) or disk_b > int(max_disk_mb_u64):
        raise RuntimeError("STRUCTURAL_DISK_CAP_EXCEEDED")
    if require_tree_hash_match_b and hash_a != hash_b:
        raise RuntimeError("STRUCTURAL_TREE_HASH_MISMATCH")

    fd_delta_a = meas_a.get("fd_delta_u64")
    fd_delta_b = meas_b.get("fd_delta_u64")
    rss_delta_a = meas_a.get("rss_delta_bytes_u64")
    rss_delta_b = meas_b.get("rss_delta_bytes_u64")
    if fd_delta_a is None or fd_delta_b is None or rss_delta_a is None or rss_delta_b is None:
        raise RuntimeError("STRUCTURAL_MEASUREMENT_MISSING")
    if int(fd_delta_a) > int(max_fd_delta_u64) or int(fd_delta_b) > int(max_fd_delta_u64):
        raise RuntimeError("STRUCTURAL_FD_DELTA_EXCEEDED")
    if int(rss_delta_a) > int(max_rss_delta_bytes_u64) or int(rss_delta_b) > int(max_rss_delta_bytes_u64):
        raise RuntimeError("STRUCTURAL_RSS_DELTA_EXCEEDED")

    receipt = {
        "schema_version": "market_rules_mutator_structural_receipt_v1",
        "soak_ticks_u64": int(soak_ticks_u64),
        "seed_u64": int(seed_u64),
        "max_fd_delta_u64": int(max_fd_delta_u64),
        "max_rss_delta_bytes_u64": int(max_rss_delta_bytes_u64),
        "tree_hash_a": str(hash_a),
        "tree_hash_b": str(hash_b),
        "disk_mb_a_u64": int(disk_a),
        "disk_mb_b_u64": int(disk_b),
        "measured_a": dict(meas_a),
        "measured_b": dict(meas_b),
    }
    return receipt, run_a


def _emit_ccap(
    *,
    repo_root: Path,
    out_dir: Path,
    patch_bytes: bytes,
    base_tree_repo_root: Path | None = None,
) -> tuple[str, str, str, str]:
    out_dir = out_dir.resolve()
    pins = load_authority_pins(repo_root)
    base_tree_root = Path(base_tree_repo_root).resolve() if base_tree_repo_root is not None else repo_root
    base_tree_id = compute_repo_base_tree_id_tolerant(base_tree_root)
    build_recipe_id = _first_build_recipe_id(repo_root)

    patch_hex = hashlib.sha256(patch_bytes).hexdigest()
    patch_blob_id = f"sha256:{patch_hex}"
    patch_relpath = f"ccap/blobs/sha256_{patch_hex}.patch"

    ccap: dict[str, Any] = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": base_tree_id,
            "auth_hash": auth_hash(pins),
            "dsbx_profile_id": str(pins["active_dsbx_profile_ids"][0]),
            "env_contract_id": str(pins["env_contract_id"]),
            "toolchain_root_id": str(pins["toolchain_root_id"]),
            "ek_id": str(pins["active_ek_id"]),
            "op_pool_id": str(pins["active_op_pool_ids"][0]),
            "canon_version_ids": dict(pins["canon_version_ids"]),
        },
        "payload": {"kind": "PATCH", "patch_blob_id": patch_blob_id},
        "build": {"build_recipe_id": build_recipe_id, "build_targets": [], "artifact_bindings": {}},
        "eval": {
            "stages": [{"stage_name": "REALIZE"}, {"stage_name": "SCORE"}, {"stage_name": "FINAL_AUDIT"}],
            "final_suite_id": "sha256:" + ("1" * 64),
        },
        "budgets": {
            "cpu_ms_max": 180_000,
            "wall_ms_max": 180_000,
            "mem_mb_max": 4096,
            "disk_mb_max": 8192,
            "fds_max": 512,
            "procs_max": 256,
            "threads_max": 512,
            "net": "forbidden",
        },
    }
    ccap_id = ccap_payload_id(ccap)
    ccap_relpath = f"ccap/sha256_{ccap_id.split(':', 1)[1]}.ccap_v1.json"

    (out_dir / "ccap" / "blobs").mkdir(parents=True, exist_ok=True)
    (out_dir / "promotion").mkdir(parents=True, exist_ok=True)
    (out_dir / "ccap").mkdir(parents=True, exist_ok=True)

    (out_dir / patch_relpath).parent.mkdir(parents=True, exist_ok=True)
    (out_dir / patch_relpath).write_bytes(patch_bytes)
    write_canon_json(out_dir / ccap_relpath, ccap)

    bundle = {
        "schema_version": "omega_promotion_bundle_ccap_v1",
        "ccap_id": ccap_id,
        "ccap_relpath": ccap_relpath,
        "patch_relpath": patch_relpath,
        "touched_paths": [ccap_relpath, patch_relpath],
        "activation_key": ccap_id,
    }
    require_no_absolute_paths(bundle)
    bundle_hash = canon_hash_obj(bundle)
    write_canon_json(
        out_dir / "promotion" / f"sha256_{bundle_hash.split(':', 1)[1]}.omega_promotion_bundle_ccap_v1.json",
        bundle,
    )
    return ccap_id, ccap_relpath, patch_relpath, bundle_hash


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    pack = load_canon_dict(campaign_pack, reason="SCHEMA_FAIL")
    if str(pack.get("schema_version", "")).strip() != _PACK_SCHEMA:
        fail("SCHEMA_FAIL")
    target_relpath = str(pack.get("target_relpath", "")).strip().replace("\\", "/").lstrip("./")
    if not target_relpath or Path(target_relpath).is_absolute() or ".." in Path(target_relpath).parts:
        fail("SCHEMA_FAIL")
    tick_u64 = max(0, int(os.environ.get("OMEGA_TICK_U64", "0") or "0"))
    if target_relpath != _LOCKED_TARGET_RELPATH:
        failure = {
            "schema_version": "market_rules_mutator_verify_failure_v1",
            "tick_u64": int(tick_u64),
            "target_relpath": target_relpath,
            "reason": "LANDING_REJECTED",
            "allowed_target_relpath": _LOCKED_TARGET_RELPATH,
        }
        failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
        write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
        return
    repo_root = Path.cwd().resolve()
    try:
        git_status_rows = _git_out(repo_root, ["status", "--porcelain"])
    except Exception as exc:  # noqa: BLE001
        failure = {
            "schema_version": "market_rules_mutator_verify_failure_v1",
            "tick_u64": int(tick_u64),
            "target_relpath": target_relpath,
            "reason": "REPO_STATUS_CHECK_FAILED",
            "detail": str(exc)[:4000],
        }
        failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
        write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
        return
    allow_dirty_b = str(os.environ.get("ORCH_MUTATOR_ALLOW_DIRTY", "0")).strip().lower() in {"1", "true", "yes", "on"}
    if git_status_rows.strip() and not allow_dirty_b:
        failure = {
            "schema_version": "market_rules_mutator_verify_failure_v1",
            "tick_u64": int(tick_u64),
            "target_relpath": target_relpath,
            "reason": "REPO_NOT_CLEAN",
            "dirty_rows_preview": git_status_rows.splitlines()[:20],
        }
        failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
        write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
        return
    target_path = (repo_root / target_relpath).resolve()
    if not target_path.exists() or not target_path.is_file():
        fail("MISSING_STATE_INPUT")
    target_text = target_path.read_text(encoding="utf-8")

    run_seed_u64 = max(0, int(os.environ.get("OMEGA_RUN_SEED_U64", "0") or "0"))

    resource_caps = pack.get("resource_caps") if isinstance(pack.get("resource_caps"), dict) else {}
    max_patch_bytes_u64 = max(1, int(resource_caps.get("max_patch_bytes_u64", 200_000)))
    max_prompt_chars_u64 = int(resource_caps.get("max_prompt_chars_u64", 200_000) or 200_000)
    max_response_chars_u64 = int(resource_caps.get("max_response_chars_u64", 400_000) or 400_000)
    wall_ms_max_u64 = max(1, int(resource_caps.get("wall_ms_max_u64", 600_000)))

    benchmark = pack.get("benchmark") if isinstance(pack.get("benchmark"), dict) else {}
    ticks_per_trial_u64 = max(1, int(benchmark.get("ticks_per_trial_u64", 15)))
    trials_u64 = max(1, int(benchmark.get("trials_u64", 5)))
    seed_base_u64 = int(benchmark.get("seed_base_u64", 424242))
    metric = str(benchmark.get("metric", "median_stps_non_noop_q32")).strip() or "median_stps_non_noop_q32"
    benchmark_deterministic_timing_b = bool(benchmark.get("deterministic_timing_b", True))

    structural = pack.get("structural_validator") if isinstance(pack.get("structural_validator"), dict) else {}
    soak_ticks_u64 = max(1, int(structural.get("soak_ticks_u64", 120)))
    require_tree_hash_match_b = bool(structural.get("require_tree_hash_match_b", True))
    max_disk_mb_u64 = max(1, int(structural.get("max_disk_mb_u64", 2048)))
    max_fd_delta_u64 = max(0, int(structural.get("max_fd_delta_u64", 50)))
    max_rss_delta_bytes_u64 = max(0, int(structural.get("max_rss_delta_bytes_u64", 268435456)))

    bench_pack_rel = str(pack.get("bench_pack_rel", _BENCH_PACK_DEFAULT)).strip() or _BENCH_PACK_DEFAULT
    bench_pack_path = (repo_root / bench_pack_rel).resolve()
    if not bench_pack_path.is_file():
        failure = {
            "schema_version": "market_rules_mutator_verify_failure_v1",
            "tick_u64": int(tick_u64),
            "target_relpath": target_relpath,
            "reason": "BENCH_PACK_MISSING",
            "bench_pack_rel": bench_pack_rel,
        }
        failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
        write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
        return
    try:
        _ = load_canon_dict(bench_pack_path, reason="SCHEMA_FAIL")
        _run_python_gate(repo_root=repo_root, args=["-c", "import cdel; import sys; print(sys.version)"])
        _run_python_gate(repo_root=repo_root, args=["-m", "py_compile", target_relpath])
        _run_python_gate(repo_root=repo_root, args=["-c", "import orchestrator.omega_bid_market_v1 as _m; print('OK')"])
    except Exception as exc:  # noqa: BLE001
        failure = {
            "schema_version": "market_rules_mutator_verify_failure_v1",
            "tick_u64": int(tick_u64),
            "target_relpath": target_relpath,
            "reason": "TOOLCHAIN_SANITY_FAIL",
            "detail": str(exc)[:4000],
        }
        failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
        write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
        return

    os.environ.setdefault("ORCH_LLM_BACKEND", "mlx")
    os.environ["ORCH_LLM_MAX_PROMPT_CHARS"] = str(int(max_prompt_chars_u64))
    os.environ["ORCH_LLM_MAX_RESPONSE_CHARS"] = str(int(max_response_chars_u64))
    os.environ["ORCH_LLM_MAX_CALLS"] = "1"
    os.environ["ORCH_LLM_SEED_U64"] = str(int(run_seed_u64))
    # Deterministic-by-construction mutator policy: greedy decode.
    os.environ["ORCH_LLM_TEMPERATURE"] = "0"
    os.environ["ORCH_LLM_TOP_P"] = "1.0"

    template_only_b = str(os.environ.get("ORCH_MUTATOR_TEMPLATE_ONLY", "0")).strip().lower() in {"1", "true", "yes", "on"}
    if template_only_b:
        try:
            patch_text = _template_patch_for_target(
                target_relpath=target_relpath,
                target_text=target_text,
                tick_u64=int(tick_u64),
            )
        except Exception as exc:  # noqa: BLE001
            failure = {
                "schema_version": "market_rules_mutator_llm_failure_v1",
                "tick_u64": int(tick_u64),
                "target_relpath": target_relpath,
                "detail": f"TEMPLATE_PATCH_FAILED:{str(exc)[:3900]}",
            }
            failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
            write_canon_json(out_dir / "market_rules_mutator_llm_failure_v1.json", failure)
            return
    else:
        try:
            backend = get_backend()
        except Exception as exc:  # noqa: BLE001
            failure = {
                "schema_version": "market_rules_mutator_llm_failure_v1",
                "tick_u64": int(tick_u64),
                "target_relpath": target_relpath,
                "detail": f"BACKEND_INIT_FAILED:{str(exc)[:3900]}",
            }
            failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
            write_canon_json(out_dir / "market_rules_mutator_llm_failure_v1.json", failure)
            return
        task = (
            "Propose a deterministic, replay-valid patch that changes only the target file. "
            "Focus on market scoring/selection/settlement behavior while preserving determinism and schema compatibility. "
            "Keep the patch small and avoid adding new dependencies."
        )
        prompt = _canonical_dumps(
            {
                "schema_version": "rsi_market_rules_mutator_prompt_v1",
                "tick_u64": int(tick_u64),
                "run_seed_u64": int(run_seed_u64),
                "task": task,
                "target_relpath": str(target_relpath),
                "constraints": {"output_format": "json", "json_schema": {"unified_diff": "string | optional", "updated_file_text": "string | optional"}},
                "target_file_text": target_text,
            }
        )
        if len(prompt) > max_prompt_chars_u64:
            prompt = prompt[: max_prompt_chars_u64]
        try:
            response = backend.generate(prompt)
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)[:4000]
            failure = {
                "schema_version": "market_rules_mutator_llm_failure_v1",
                "tick_u64": int(tick_u64),
                "target_relpath": target_relpath,
                "detail": detail,
            }
            failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
            write_canon_json(out_dir / "market_rules_mutator_llm_failure_v1.json", failure)
            return
        if len(response) > max_response_chars_u64:
            response = response[: max_response_chars_u64]
        patch_text = None
        try:
            obj = _extract_json_obj(str(response or ""))
            if isinstance(obj.get("unified_diff"), str) and str(obj.get("unified_diff", "")).strip():
                patch_text = str(obj["unified_diff"])
            elif isinstance(obj.get("patch"), str) and str(obj.get("patch", "")).strip():
                patch_text = str(obj["patch"])
            elif isinstance(obj.get("diff"), str) and str(obj.get("diff", "")).strip():
                patch_text = str(obj["diff"])
            updated = obj.get("updated_file_text") if isinstance(obj, dict) else None
            if patch_text is None and isinstance(updated, str) and updated.strip():
                required_markers = ["def select_winner", "def settle_and_advance_market_state", "def bid_market_enabled"]
                if len(updated) < int(0.80 * len(target_text)) or any(marker not in updated for marker in required_markers):
                    failure = {
                        "schema_version": "market_rules_mutator_verify_failure_v1",
                        "tick_u64": int(tick_u64),
                        "target_relpath": target_relpath,
                        "reason": "UPDATED_FILE_TEXT_INVARIANT_FAIL",
                        "detail": "missing required markers or too short",
                        "updated_chars_u64": int(len(updated)),
                        "target_chars_u64": int(len(target_text)),
                    }
                    failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                    write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
                    return
                patch_text = _diff_from_updated_text(target_relpath=target_relpath, before=target_text, after=updated)
        except Exception:
            patch_text = None

        if patch_text is None:
            patch_text = _extract_unified_diff_text(str(response or ""))
        if patch_text is None:
            failure = {
                "schema_version": "market_rules_mutator_llm_failure_v1",
                "tick_u64": int(tick_u64),
                "target_relpath": target_relpath,
                "detail": "LLM_RESPONSE_INVALID",
            }
            failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
            write_canon_json(out_dir / "market_rules_mutator_llm_failure_v1.json", failure)
            return
    patch_text = _ensure_patch_headers(patch_text, target_relpath=target_relpath)
    patch_bytes = patch_text.encode("utf-8")
    if len(patch_bytes) > max_patch_bytes_u64:
        failure = {
            "schema_version": "market_rules_mutator_verify_failure_v1",
            "tick_u64": int(tick_u64),
            "target_relpath": target_relpath,
            "reason": "PATCH_TOO_LARGE",
            "patch_bytes_u64": int(len(patch_bytes)),
            "max_patch_bytes_u64": int(max_patch_bytes_u64),
        }
        failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
        write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
        return

    touched = _parse_patch_touched_paths(patch_bytes)
    if set(touched) != {target_relpath}:
        failure = {
            "schema_version": "market_rules_mutator_verify_failure_v1",
            "tick_u64": int(tick_u64),
            "target_relpath": target_relpath,
            "reason": "TOUCHED_PATHS_MISMATCH",
            "touched_paths": touched,
        }
        failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
        write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
        return

    reports_dir = out_dir / "daemon" / "rsi_market_rules_mutator_v1" / "state" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="phase3_market_mutator_", dir=str(out_dir)) as scratch_raw:
        scratch = Path(scratch_raw)
        baseline_wt = scratch / "baseline"
        candidate_wt = scratch / "candidate"
        _git(repo_root, ["worktree", "add", "--detach", str(baseline_wt), "HEAD"])
        _git(repo_root, ["worktree", "add", "--detach", str(candidate_wt), "HEAD"])
        try:
            patch_path = scratch / "candidate.patch"
            patch_path.write_bytes(patch_bytes)
            try:
                _git(candidate_wt, ["apply", "--check", "-p1", str(patch_path)])
                _git(candidate_wt, ["apply", "-p1", str(patch_path)])
            except Exception as exc:  # noqa: BLE001
                recovered = False
                try:
                    _git(candidate_wt, ["apply", "--check", "--recount", "--ignore-whitespace", "-p1", str(patch_path)])
                    _git(candidate_wt, ["apply", "--recount", "--ignore-whitespace", "-p1", str(patch_path)])
                    recovered = True
                except Exception:
                    recovered = False
                if not recovered:
                    repaired = _repair_patch_prefix_that_applies(worktree=candidate_wt, patch_bytes=patch_bytes)
                    if repaired is None:
                        failure = {
                            "schema_version": "market_rules_mutator_patch_apply_failure_v1",
                            "tick_u64": int(tick_u64),
                            "target_relpath": target_relpath,
                            "detail": str(exc)[:4000],
                        }
                        failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                        write_canon_json(out_dir / "market_rules_mutator_patch_apply_failure_v1.json", failure)
                        return
                    patch_bytes = repaired
                    touched = _parse_patch_touched_paths(patch_bytes)
                    if set(touched) != {target_relpath}:
                        failure = {
                            "schema_version": "market_rules_mutator_verify_failure_v1",
                            "tick_u64": int(tick_u64),
                            "target_relpath": target_relpath,
                            "reason": "TOUCHED_PATHS_MISMATCH",
                            "touched_paths": touched,
                        }
                        failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                        write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
                        return
                    patch_path.write_bytes(patch_bytes)
                    _git(candidate_wt, ["apply", "--check", "--recount", "--ignore-whitespace", "-p1", str(patch_path)])
                    _git(candidate_wt, ["apply", "--recount", "--ignore-whitespace", "-p1", str(patch_path)])
            try:
                patch_bytes = _canonical_patch_from_worktree(worktree=candidate_wt, target_relpath=target_relpath)
            except Exception as exc:  # noqa: BLE001
                failure = {
                    "schema_version": "market_rules_mutator_verify_failure_v1",
                    "tick_u64": int(tick_u64),
                    "target_relpath": target_relpath,
                    "reason": "CANONICAL_PATCH_REBUILD_FAILED",
                    "detail": str(exc)[:4000],
                }
                failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
                return
            touched = _parse_patch_touched_paths(patch_bytes)
            if set(touched) != {target_relpath}:
                failure = {
                    "schema_version": "market_rules_mutator_verify_failure_v1",
                    "tick_u64": int(tick_u64),
                    "target_relpath": target_relpath,
                    "reason": "TOUCHED_PATHS_MISMATCH",
                    "touched_paths": touched,
                }
                failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
                return
            candidate_target = (candidate_wt / target_relpath).resolve()
            baseline_target = (baseline_wt / target_relpath).resolve()
            try:
                candidate_text = candidate_target.read_text(encoding="utf-8")
                ast.parse(candidate_text, filename=target_relpath)
                baseline_text = baseline_target.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                failure = {
                    "schema_version": "market_rules_mutator_verify_failure_v1",
                    "tick_u64": int(tick_u64),
                    "target_relpath": target_relpath,
                    "reason": "CANDIDATE_SYNTAX_ERROR",
                    "detail": str(exc)[:4000],
                }
                failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
                return

            nontrivial_reason = _patch_nontrivial_reason(
                before_text=baseline_text,
                after_text=candidate_text,
                patch_bytes=patch_bytes,
            )
            if nontrivial_reason is not None:
                failure = {
                    "schema_version": "market_rules_mutator_verify_failure_v1",
                    "tick_u64": int(tick_u64),
                    "target_relpath": target_relpath,
                    "reason": str(nontrivial_reason),
                }
                failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
                return
            try:
                _run_python_gate(repo_root=candidate_wt, args=["-m", "py_compile", target_relpath])
                _run_python_gate(repo_root=candidate_wt, args=["-c", "import orchestrator.omega_bid_market_v1 as _m; print('OK')"])
            except Exception as exc:  # noqa: BLE001
                failure = {
                    "schema_version": "market_rules_mutator_verify_failure_v1",
                    "tick_u64": int(tick_u64),
                    "target_relpath": target_relpath,
                    "reason": "CANDIDATE_IMPORT_ERROR",
                    "detail": str(exc)[:4000],
                }
                failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
                return
            try:
                micro_receipt = _micro_bench_gate(
                    baseline_worktree=baseline_wt,
                    candidate_worktree=candidate_wt,
                    bench_pack_rel=bench_pack_rel,
                    seed_u64=int(seed_base_u64),
                    deterministic_timing_b=benchmark_deterministic_timing_b,
                    out_dir=out_dir,
                    wall_ms_max_u64=wall_ms_max_u64,
                )
            except Exception as exc:  # noqa: BLE001
                failure = {
                    "schema_version": "market_rules_mutator_verify_failure_v1",
                    "tick_u64": int(tick_u64),
                    "target_relpath": target_relpath,
                    "reason": "MICRO_BENCH_GATE_FAIL",
                    "detail": str(exc)[:4000],
                }
                failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
                return
            micro_receipt["receipt_id"] = canon_hash_obj({k: v for k, v in micro_receipt.items() if k != "receipt_id"})
            write_canon_json(out_dir / "market_rules_mutator_micro_bench_receipt_v1.json", micro_receipt)

            improvements: list[float] = []
            trials_out: list[dict[str, Any]] = []
            winner_trial_rows: list[dict[str, Any]] = []
            for idx in range(int(trials_u64)):
                seed = int(seed_base_u64) + idx
                base_state = _run_daemon_loop(
                    repo_root=baseline_wt,
                    campaign_pack_rel=bench_pack_rel,
                    out_root=out_dir / "bench" / f"trial_{idx+1:02d}" / "baseline",
                    tick_start_u64=1,
                    ticks_u64=ticks_per_trial_u64,
                    run_seed_u64=seed,
                    deterministic_timing=bool(benchmark_deterministic_timing_b),
                )
                cand_state = _run_daemon_loop(
                    repo_root=candidate_wt,
                    campaign_pack_rel=bench_pack_rel,
                    out_root=out_dir / "bench" / f"trial_{idx+1:02d}" / "candidate",
                    tick_start_u64=1,
                    ticks_u64=ticks_per_trial_u64,
                    run_seed_u64=seed,
                    deterministic_timing=bool(benchmark_deterministic_timing_b),
                )
                base_score = _score_metric_q32(base_state, metric=metric)
                cand_score = _score_metric_q32(cand_state, metric=metric)
                improvement = (float(cand_score) - float(base_score)) / max(float(base_score), 1e-9)
                improvements.append(float(improvement))
                baseline_winners = _winner_sequence_from_state(base_state)
                candidate_winners = _winner_sequence_from_state(cand_state)
                winner_delta = _winner_dynamics_trial_delta(
                    baseline_seq=baseline_winners,
                    candidate_seq=candidate_winners,
                )
                winner_trial_rows.append(
                    {
                        "trial_u64": int(idx + 1),
                        "seed_u64": int(seed),
                        "baseline_winner_sequence": baseline_winners,
                        "candidate_winner_sequence": candidate_winners,
                        "changed_b": bool(winner_delta.get("changed_b", False)),
                        "first_delta": winner_delta.get("first_delta"),
                    }
                )
                trials_out.append(
                    {
                        "trial_u64": int(idx + 1),
                        "seed_u64": int(seed),
                        "baseline_score_q32": int(base_score),
                        "candidate_score_q32": int(cand_score),
                        "improvement_frac_f64": _fmt_f64(float(improvement)),
                    }
                )

            bench_receipt = {
                "schema_version": "market_rules_mutator_bench_receipt_v1",
                "tick_u64": int(tick_u64),
                "target_relpath": target_relpath,
                "metric": metric,
                "ticks_per_trial_u64": int(ticks_per_trial_u64),
                "trials_u64": int(trials_u64),
                "seed_base_u64": int(seed_base_u64),
                "deterministic_timing_b": bool(benchmark_deterministic_timing_b),
                "trials": trials_out,
                "median_improvement_frac_f64": _fmt_f64(float(_median(improvements))),
            }
            bench_receipt["receipt_id"] = canon_hash_obj({k: v for k, v in bench_receipt.items() if k != "receipt_id"})
            write_canon_json(out_dir / "market_rules_mutator_bench_receipt_v1.json", bench_receipt)

            changed_trials = [row for row in winner_trial_rows if bool(row.get("changed_b", False))]
            first_changed_trial = changed_trials[0] if changed_trials else None
            dynamics_payload = {
                "schema_version": "market_winner_dynamics_v1",
                "tick_u64": int(tick_u64),
                "target_relpath": target_relpath,
                "required_min_changed_trials_u64": 1,
                "trials_u64": int(trials_u64),
                "changed_trials_u64": int(len(changed_trials)),
                "acceptance_pass_b": bool(len(changed_trials) >= 1),
                "first_changed_trial_u64": (None if first_changed_trial is None else int(first_changed_trial.get("trial_u64", 0))),
                "first_delta": (None if first_changed_trial is None else first_changed_trial.get("first_delta")),
                "trials": winner_trial_rows,
            }
            dynamics_payload["report_id"] = canon_hash_obj({k: v for k, v in dynamics_payload.items() if k != "report_id"})
            write_canon_json(out_dir / "market_winner_dynamics_v1.json", dynamics_payload)
            if not dynamics_payload["acceptance_pass_b"]:
                failure = {
                    "schema_version": "market_rules_mutator_verify_failure_v1",
                    "tick_u64": int(tick_u64),
                    "target_relpath": target_relpath,
                    "reason": "WINNER_DYNAMICS_UNCHANGED",
                    "changed_trials_u64": int(len(changed_trials)),
                    "required_min_changed_trials_u64": 1,
                }
                failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                write_canon_json(out_dir / "market_rules_mutator_verify_failure_v1.json", failure)
                return

            try:
                structural_receipt, structural_state_dir = _structural_validate(
                    candidate_worktree=candidate_wt,
                    bench_pack_rel=bench_pack_rel,
                    soak_ticks_u64=soak_ticks_u64,
                    seed_u64=int(seed_base_u64),
                    max_disk_mb_u64=max_disk_mb_u64,
                    max_fd_delta_u64=max_fd_delta_u64,
                    max_rss_delta_bytes_u64=max_rss_delta_bytes_u64,
                    require_tree_hash_match_b=require_tree_hash_match_b,
                    out_dir=out_dir,
                )
            except Exception as exc:  # noqa: BLE001
                failure = {
                    "schema_version": "market_rules_mutator_structural_failure_v1",
                    "tick_u64": int(tick_u64),
                    "target_relpath": target_relpath,
                    "detail": str(exc)[:4000],
                }
                failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                write_canon_json(out_dir / "market_rules_mutator_structural_failure_v1.json", failure)
                return
            structural_receipt["receipt_id"] = canon_hash_obj(
                {k: v for k, v in structural_receipt.items() if k != "receipt_id"}
            )
            write_canon_json(out_dir / "market_rules_mutator_structural_receipt_v1.json", structural_receipt)

            verdict = _run_v19_replay_verdict(repo_root=candidate_wt, state_dir=structural_state_dir)
            if verdict != "VALID":
                failure = {
                    "schema_version": "market_rules_mutator_replay_failure_v1",
                    "tick_u64": int(tick_u64),
                    "target_relpath": target_relpath,
                    "detail": str(verdict)[:4000],
                }
                failure["failure_id"] = canon_hash_obj({k: v for k, v in failure.items() if k != "failure_id"})
                write_canon_json(out_dir / "market_rules_mutator_replay_failure_v1.json", failure)
                return

            ccap_id, _ccap_relpath, _patch_relpath, bundle_hash = _emit_ccap(
                repo_root=repo_root,
                out_dir=out_dir,
                patch_bytes=patch_bytes,
            )
            report = {
                "schema_version": "market_rules_mutator_report_v1",
                "tick_u64": int(tick_u64),
                "target_relpath": target_relpath,
                "ccap_id": ccap_id,
                "bundle_hash": bundle_hash,
                "patch_sha256": _sha256_prefixed(patch_bytes),
                "touched_paths": touched,
                "winner_dynamics_relpath": "market_winner_dynamics_v1.json",
                "winner_dynamics_changed_trials_u64": int(len(changed_trials)),
            }
            require_no_absolute_paths(report)
            report["report_id"] = canon_hash_obj({k: v for k, v in report.items() if k != "report_id"})
            write_canon_json(reports_dir / "market_rules_mutator_report_v1.json", report)
        finally:
            try:
                _git(repo_root, ["worktree", "remove", "-f", str(baseline_wt)])
            except Exception:
                pass
            try:
                _git(repo_root, ["worktree", "remove", "-f", str(candidate_wt)])
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rsi_market_rules_mutator_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args(argv)
    run(campaign_pack=Path(args.campaign_pack).resolve(), out_dir=Path(args.out_dir).resolve())
    sys.stdout.write("OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
