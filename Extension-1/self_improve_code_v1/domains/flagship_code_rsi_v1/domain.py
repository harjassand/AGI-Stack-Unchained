"""Flagship code RSI domain runner (v1.3)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ...canon.json_canon_v1 import canon_bytes
from ...canon.hash_v1 import sha256_hex
from ...devscreen.workspace_v1 import create_workspace, remove_workspace
from ...ops.token_edit_v1 import read_text_normalized
from ...patch.unified_diff_v1 import unified_diff
from ...package.tar_deterministic_v1 import write_deterministic_tar

from .candidate_v1 import build_manifest
from .curriculum_v1 import (
    init_state as init_curriculum_state,
    ladder_from_config,
    select_active_tier,
    tier_info,
    update_state as update_curriculum_state,
)
from .devscreen_v1 import run_devscreen
from .fail_signature_v1 import failure_signature
from .noop_guard_v1 import is_semantic_noop
from .patch_templates_v1 import DevHint, get_template, template_ids
from .proposer_v1 import derive_rng, load_state, save_state, update_state
from .scoreboard_v1 import build_run_manifest, init_scoreboard, update_scoreboard
from .sealed_eval_client_v1 import run_sealed_eval
from .selection_v1 import rank_for_submission, select_topk_for_submission


_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")


class _EpochAbort(RuntimeError):
    def __init__(self, where: str) -> None:
        super().__init__(where)
        self.where = where


def _resolve_path(base_dir: str, path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base_dir, path))


def _parse_json(path: str) -> Dict:
    with open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"), parse_float=Decimal)


def _format_decimal(value: Decimal) -> str:
    if value.is_nan() or value.is_infinite():
        raise ValueError("invalid decimal")
    tup = value.as_tuple()
    digits = "".join(str(d) for d in tup.digits) or "0"
    exp = tup.exponent
    if exp >= 0:
        int_part = digits + ("0" * exp)
        frac_part = ""
    else:
        split = len(digits) + exp
        if split > 0:
            int_part = digits[:split]
            frac_part = digits[split:]
        else:
            int_part = "0"
            frac_part = ("0" * (-split)) + digits
    int_part = int_part.lstrip("0") or "0"
    frac_part = frac_part.rstrip("0")
    rendered = f"{int_part}.{frac_part}" if frac_part else int_part
    return f"-{rendered}" if value.is_signed() and rendered != "0" else rendered


def _normalize_for_hash(obj):
    if isinstance(obj, Decimal):
        return _format_decimal(obj)
    if isinstance(obj, float):
        return _format_decimal(Decimal(str(obj)))
    if isinstance(obj, dict):
        return {str(k): _normalize_for_hash(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_for_hash(v) for v in obj]
    return obj


def _fraction(value) -> Tuple[int, int]:
    if isinstance(value, int):
        return value, 1
    if isinstance(value, Decimal):
        return _decimal_to_fraction(value)
    if isinstance(value, float):
        return _decimal_to_fraction(Decimal(str(value)))
    if isinstance(value, str):
        if "/" in value:
            num, den = value.split("/", 1)
            return int(num), max(1, int(den))
        return _decimal_to_fraction(Decimal(value))
    return int(value), 1


def _decimal_to_fraction(value: Decimal) -> Tuple[int, int]:
    tup = value.as_tuple()
    digits = int("".join(str(d) for d in tup.digits) or "0")
    if tup.exponent >= 0:
        num = digits * (10 ** tup.exponent)
        den = 1
    else:
        den = 10 ** (-tup.exponent)
        num = digits
    if tup.sign:
        num = -num
    return num, den


def resolve_baseline_commit(repo_root: str, baseline_commit: str) -> str:
    if baseline_commit == "PIN_THIS_40_HEX":
        proc = subprocess.run(["git", "-C", repo_root, "rev-parse", "HEAD"], capture_output=True, check=True)
        baseline_commit = (proc.stdout or b"").decode("utf-8").strip()
    if not _HEX40_RE.match(baseline_commit or ""):
        raise SystemExit("baseline_commit must be 40-hex")
    proc = subprocess.run(["git", "-C", repo_root, "cat-file", "-e", baseline_commit], capture_output=True)
    if proc.returncode != 0:
        raise SystemExit("baseline_commit not present in target repo")
    return baseline_commit


def _compute_run_id(config_hash: str) -> str:
    return sha256_hex(("flagship_code_rsi_v1\0" + config_hash).encode("utf-8"))


def _extract_paths_from_patch(patch_text: str) -> List[str]:
    paths: List[str] = []
    for line in patch_text.splitlines():
        if line.startswith("+++ b/"):
            rel = line[len("+++ b/") :].strip()
            if rel and rel not in paths:
                paths.append(rel)
    return paths


def _write_json(path: str, payload: Dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(canon_bytes(payload))


def _write_json_atomic(path: str, payload: Dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(canon_bytes(payload))
    os.replace(tmp_path, path)


def _load_run_config(path: str) -> Dict:
    cfg = _parse_json(path)
    if cfg.get("schema_version") != "flagship_code_rsi_v1":
        raise SystemExit("run_config schema_version must be flagship_code_rsi_v1")
    return cfg


def _normalize_config(cfg: Dict, base_dir: str) -> Dict:
    cfg = dict(cfg)
    cfg.setdefault("run_id", "AUTO")
    cfg.setdefault("seed", 1)
    if "run_wall_timeout_s" not in cfg and "wall_timeout_s" in cfg:
        cfg["run_wall_timeout_s"] = cfg.get("wall_timeout_s", 0)
    cfg.setdefault("run_wall_timeout_s", 0)
    cfg.setdefault("epoch_wall_timeout_s", 0)
    cfg.setdefault("output", {})
    cfg.setdefault("candidate", {})
    cfg.setdefault("proposal", {})
    cfg.setdefault("devscreen", {})
    cfg.setdefault("sealed_dev", {})
    cfg.setdefault("sealed_heldout", {})
    cfg.setdefault("curriculum", {})

    cfg["target_repo_path"] = _resolve_path(base_dir, cfg.get("target_repo_path", ""))
    cfg["output"]["runs_root"] = _resolve_path(base_dir, cfg["output"].get("runs_root", "runs"))

    cfg["proposal"].setdefault("candidates_per_epoch", 32)
    cfg["proposal"].setdefault("topk_to_sealed_dev", 4)
    cfg["proposal"].setdefault("explore_fraction", "0.25")
    cfg["proposal"].setdefault("max_attempts_per_slot", 10)
    cfg["proposal"].setdefault("max_total_attempts", 800)
    cfg["proposal"].setdefault("min_eligible_per_epoch", 4)
    cfg["proposal"].setdefault("template_allowlist", [])

    cfg["curriculum"].setdefault("advance_rule", {"type": "pass_rate_threshold", "threshold": "0.70", "min_epochs": 2})
    cfg["curriculum"].setdefault("min_submissions_before_advancing", 20)
    cfg["curriculum"].setdefault("deescalate_after_epochs", 3)
    cfg["curriculum"].setdefault("rolling_window", 5)

    cfg["devscreen"].setdefault("max_evals_per_epoch", 0)

    return cfg


def _is_text_file(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
        if b"\x00" in chunk:
            return False
    except OSError:
        return False
    return True


def _list_repo_files(repo_dir: str) -> List[str]:
    out: List[str] = []
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in {".git", "__pycache__", "node_modules", "dist", "build", ".venv", "venv", "runs"}
        )
        for name in sorted(files):
            rel = os.path.relpath(os.path.join(root, name), repo_dir)
            out.append(rel)
    return out


def _select_text_file(repo_dir: str) -> Optional[str]:
    candidates: List[str] = []
    for rel in _list_repo_files(repo_dir):
        if rel.endswith(".py"):
            abs_path = os.path.join(repo_dir, rel)
            if _is_text_file(abs_path):
                candidates.append(rel)
    if not candidates:
        for rel in _list_repo_files(repo_dir):
            abs_path = os.path.join(repo_dir, rel)
            if _is_text_file(abs_path):
                candidates.append(rel)
    if not candidates:
        return None
    return sorted(candidates)[0]


def _build_noop_patch(relpath: str, line: str, line_num: int) -> str:
    header = [
        f"diff --git a/{relpath} b/{relpath}",
        f"--- a/{relpath}",
        f"+++ b/{relpath}",
        f"@@ -{line_num},1 +{line_num},1 @@",
        f"-{line}",
        f"+{line}",
    ]
    return "\n".join(header) + "\n"


def _build_comment_patch(relpath: str, original: str, comment: str) -> str:
    if original.endswith("\n"):
        updated = original + comment + "\n"
    else:
        updated = original + "\n" + comment + "\n"
    return unified_diff({relpath: (original, updated)})


def _write_candidate_bundle(cand_dir: str, manifest: Dict, patch_bytes: bytes) -> Dict[str, str]:
    os.makedirs(cand_dir, exist_ok=True)
    patch_path = os.path.join(cand_dir, "patch.diff")
    manifest_path = os.path.join(cand_dir, "manifest.json")
    tar_path = os.path.join(cand_dir, "candidate.tar")
    with open(patch_path, "wb") as f:
        f.write(patch_bytes)
    with open(manifest_path, "wb") as f:
        f.write(canon_bytes(manifest))
    write_deterministic_tar(tar_path, {"manifest.json": canon_bytes(manifest), "patch.diff": patch_bytes})
    return {"patch_path": patch_path, "manifest_path": manifest_path, "tar_path": tar_path}


def build_identity_candidate(
    *,
    repo_root: str,
    base_commit: str,
    target_repo_id: str,
    eval_plan_id: str,
    patch_format: str,
    out_dir: str,
) -> Dict:
    tmp_dir = os.path.join(out_dir, "_tmp_identity")
    create_workspace(repo_root, base_commit, tmp_dir)
    try:
        relpath = _select_text_file(tmp_dir)
        if not relpath:
            patch_text = ""
        else:
            abs_path = os.path.join(tmp_dir, relpath)
            original = read_text_normalized(abs_path)
            lines = original.splitlines()
            line = ""
            line_num = 1
            for idx, item in enumerate(lines):
                line_num = idx + 1
                line = item
                if item != "":
                    break
            patch_text = _build_noop_patch(relpath, line, line_num)
    finally:
        remove_workspace(tmp_dir)

    patch_bytes = patch_text.encode("utf-8")
    manifest = build_manifest(
        base_commit=base_commit,
        eval_plan_id=eval_plan_id,
        patch_bytes=patch_bytes,
        target_repo_id=target_repo_id,
        patch_format=patch_format,
    )
    cand_dir = os.path.join(out_dir, manifest["candidate_id"])
    paths = _write_candidate_bundle(cand_dir, manifest, patch_bytes)
    return {
        "candidate_id": manifest["candidate_id"],
        "patch_text": patch_text,
        "patch_path": paths["patch_path"],
        "manifest_path": paths["manifest_path"],
        "tar_path": paths["tar_path"],
        "candidate_dir": cand_dir,
    }


def build_null_control_candidate(
    *,
    repo_root: str,
    base_commit: str,
    target_repo_id: str,
    eval_plan_id: str,
    patch_format: str,
    out_dir: str,
) -> Dict:
    tmp_dir = os.path.join(out_dir, "_tmp_null_control")
    create_workspace(repo_root, base_commit, tmp_dir)
    try:
        relpath = _select_text_file(tmp_dir)
        if not relpath:
            patch_text = ""
        else:
            abs_path = os.path.join(tmp_dir, relpath)
            original = read_text_normalized(abs_path)
            patch_text = _build_comment_patch(relpath, original, "# null control")
    finally:
        remove_workspace(tmp_dir)

    patch_bytes = patch_text.encode("utf-8")
    manifest = build_manifest(
        base_commit=base_commit,
        eval_plan_id=eval_plan_id,
        patch_bytes=patch_bytes,
        target_repo_id=target_repo_id,
        patch_format=patch_format,
    )
    cand_dir = os.path.join(out_dir, manifest["candidate_id"])
    paths = _write_candidate_bundle(cand_dir, manifest, patch_bytes)
    return {
        "candidate_id": manifest["candidate_id"],
        "patch_text": patch_text,
        "patch_path": paths["patch_path"],
        "manifest_path": paths["manifest_path"],
        "tar_path": paths["tar_path"],
        "candidate_dir": cand_dir,
    }


def _compute_apply_proof(
    *,
    repo_root: str,
    base_commit: str,
    patch_path: str,
    patch_text: str,
    candidate_id: str,
    tmp_dir: str,
) -> Dict:
    apply_dir = os.path.join(tmp_dir, "apply_proof")
    create_workspace(repo_root, base_commit, apply_dir)
    changed_paths = _extract_paths_from_patch(patch_text)
    actual_changed = list(changed_paths)
    before: Dict[str, str] = {}
    for rel in changed_paths:
        abs_path = os.path.join(apply_dir, rel)
        if _is_text_file(abs_path):
            try:
                before[rel] = read_text_normalized(abs_path)
            except OSError:
                before[rel] = ""
        else:
            before[rel] = ""

    applies_cleanly = False
    diff_text = ""
    try:
        proc = subprocess.run(["git", "apply", "--check", patch_path], cwd=apply_dir, capture_output=True)
        applies_cleanly = proc.returncode == 0
        if applies_cleanly:
            subprocess.run(["git", "apply", patch_path], cwd=apply_dir, check=True, capture_output=True)
            diff_inputs: Dict[str, Tuple[str, str]] = {}
            for rel in sorted(changed_paths):
                abs_path = os.path.join(apply_dir, rel)
                after = ""
                if _is_text_file(abs_path):
                    try:
                        after = read_text_normalized(abs_path)
                    except OSError:
                        after = ""
                if before.get(rel, "") != after:
                    diff_inputs[rel] = (before.get(rel, ""), after)
            if diff_inputs:
                diff_text = unified_diff(diff_inputs)
            actual_changed = sorted(diff_inputs.keys())
    finally:
        remove_workspace(apply_dir)

    diff_sha = sha256_hex(diff_text.encode("utf-8"))
    tree_fingerprint = sha256_hex(("\n".join(actual_changed) + "\n" + diff_sha).encode("utf-8"))
    return {
        "candidate_id": candidate_id,
        "applies_cleanly": bool(applies_cleanly),
        "changed_paths": actual_changed,
        "diff_sha256": diff_sha,
        "repo_tree_delta_sha256": tree_fingerprint,
    }


def _primary_exception(normalized_log: str) -> str:
    for line in normalized_log.splitlines():
        if "Error" in line or "Exception" in line:
            return line
    return ""


def _synthetic_candidate_id(seed: int, epoch: int, slot: int) -> str:
    payload = f"no_patch\0{seed}\0{epoch}\0{slot}".encode("utf-8")
    return sha256_hex(payload)


def _shuffle_templates(items: List[str], rng) -> List[str]:
    out = list(items)
    for i in range(len(out) - 1, 0, -1):
        j = rng.randbelow(i + 1)
        out[i], out[j] = out[j], out[i]
    return out


def _select_devscreen_eval_set(candidates: List[Dict], max_evals: int) -> Tuple[List[str], Dict[str, str]]:
    max_evals = int(max_evals or 0)
    if max_evals <= 0:
        max_evals = len(candidates)

    selected: List[str] = []
    reasons: Dict[str, str] = {}
    selected_templates: set[str] = set()

    def _sort_key(rec: Dict) -> tuple:
        return (int(rec.get("patch_bytes", 0)), str(rec.get("candidate_id", "")))

    def _add(rec: Dict, reason: str) -> None:
        cid = str(rec.get("candidate_id", ""))
        if not cid or cid in reasons:
            return
        selected.append(cid)
        reasons[cid] = reason
        tid = str(rec.get("template_id", ""))
        if tid:
            selected_templates.add(tid)

    memory = [r for r in candidates if r.get("mode") == "exploit"]
    for rec in sorted(memory, key=_sort_key):
        if len(selected) >= max_evals:
            break
        _add(rec, "memory_mode")

    if len(selected) < max_evals:
        by_template: Dict[str, List[Dict]] = {}
        for rec in candidates:
            tid = str(rec.get("template_id", ""))
            by_template.setdefault(tid, []).append(rec)
        for tid in sorted(by_template.keys()):
            if len(selected) >= max_evals:
                break
            if tid and tid in selected_templates:
                continue
            for rec in sorted(by_template[tid], key=_sort_key):
                if rec.get("candidate_id") in reasons:
                    continue
                _add(rec, f"operator:{tid}" if tid else "operator:unknown")
                break

    if len(selected) < max_evals:
        for rec in sorted(candidates, key=_sort_key):
            if len(selected) >= max_evals:
                break
            _add(rec, "smallest_patch")

    return selected, reasons


def _distance_delta(baseline: Dict, candidate: Dict) -> Dict[str, int]:
    return {
        "failing_tests": int(candidate.get("failing_tests", 0)) - int(baseline.get("failing_tests", 0)),
        "errors": int(candidate.get("errors", 0)) - int(baseline.get("errors", 0)),
    }


def _ratio(num: int, den: int) -> str:
    if den <= 0:
        return "0/1"
    return f"{int(num)}/{int(den)}"


def _stub_sealed_result(candidate_id: str, sealed_mode: str, note: str) -> Dict:
    return {
        "candidate_id": candidate_id,
        "sealed_mode": sealed_mode,
        "status": "FAIL",
        "receipt_path": "",
        "summary": {"note": note},
    }


def run_flagship(
    config_path: str,
    epochs: int,
    heldout: bool = False,
    wall_timeout_s: int | None = None,
    epoch_wall_timeout_s: int | None = None,
    calibrate_only: bool = False,
) -> str:
    base_dir = os.path.dirname(os.path.abspath(config_path))
    raw_cfg = _load_run_config(config_path)
    cfg = _normalize_config(raw_cfg, base_dir)

    import time
    run_start = time.monotonic()
    run_wall_limit = int(
        wall_timeout_s
        or cfg.get("run_wall_timeout_s", 0)
        or cfg.get("wall_timeout_s", 0)
        or 0
    )
    epoch_wall_limit = int(epoch_wall_timeout_s or cfg.get("epoch_wall_timeout_s", 0) or 0)
    timeout_info = {"status": "OK", "where": ""}

    def _check_run_timeout(where: str) -> bool:
        if run_wall_limit <= 0:
            return False
        if time.monotonic() - run_start >= run_wall_limit:
            timeout_info["status"] = "TIMEOUT"
            timeout_info["where"] = where
            return True
        return False

    target_repo_path = cfg["target_repo_path"]
    baseline_commit = resolve_baseline_commit(target_repo_path, str(cfg.get("baseline_commit", "")))

    cfg_hash_payload = _normalize_for_hash(cfg)
    config_hash = sha256_hex(canon_bytes(cfg_hash_payload))

    run_id = cfg.get("run_id", "AUTO")
    if not run_id or run_id == "AUTO":
        run_id = _compute_run_id(config_hash)

    run_dir = os.path.join(cfg["output"]["runs_root"], run_id)
    epochs_dir = os.path.join(run_dir, "epochs")
    state_dir = os.path.join(run_dir, "state")
    if os.path.exists(run_dir):
        raise SystemExit("run_dir already exists")

    os.makedirs(epochs_dir, exist_ok=False)
    os.makedirs(state_dir, exist_ok=True)

    extension_commit = ""
    try:
        ext_root = os.path.abspath(os.path.join(base_dir, ".."))
        proc = subprocess.run(["git", "-C", ext_root, "rev-parse", "HEAD"], capture_output=True, check=True)
        extension_commit = (proc.stdout or b"").decode("utf-8").strip()
    except Exception:
        extension_commit = ""

    suite_ids = {
        "devscreen": str(cfg.get("devscreen", {}).get("suite_id", "")),
        "sealed_dev": str(cfg.get("sealed_dev", {}).get("eval_plan_id", "")),
        "sealed_heldout": str(cfg.get("sealed_heldout", {}).get("eval_plan_id", "")),
    }

    manifest = build_run_manifest(
        run_id=run_id,
        baseline_commit=baseline_commit,
        config_hash=config_hash,
        extension_commit=extension_commit,
        suite_ids=suite_ids,
    )
    _write_json(os.path.join(run_dir, "run_manifest.json"), manifest)
    _write_json(os.path.join(run_dir, "run_config.json"), _normalize_for_hash(cfg))

    scoreboard = init_scoreboard(run_id)

    state_path = os.path.join(state_dir, "proposer_state.json")
    proposer_state = load_state(state_path)

    curriculum_cfg = cfg.get("curriculum", {})
    ladder = ladder_from_config(curriculum_cfg)

    dev_cfg = cfg.get("devscreen", {})
    proposal_cfg = cfg.get("proposal", {})
    cand_cfg = cfg.get("candidate", {})
    sealed_dev_cfg = cfg.get("sealed_dev", {})
    sealed_heldout_cfg = cfg.get("sealed_heldout", {})

    candidates_per_epoch = int(proposal_cfg.get("candidates_per_epoch", 0))
    topk_to_sealed = int(proposal_cfg.get("topk_to_sealed_dev", 0))
    explore_fraction = _fraction(proposal_cfg.get("explore_fraction", 0))
    max_attempts_per_slot = int(proposal_cfg.get("max_attempts_per_slot", 10))
    max_total_attempts = int(proposal_cfg.get("max_total_attempts", 800))
    min_eligible_per_epoch = int(proposal_cfg.get("min_eligible_per_epoch", 0))
    template_allowlist = [str(t) for t in proposal_cfg.get("template_allowlist", []) or [] if str(t)]
    template_pool = [tid for tid in template_ids() if not template_allowlist or tid in template_allowlist]

    max_patch_bytes = int(cand_cfg.get("max_patch_bytes", 0))
    patch_format = str(cand_cfg.get("patch_format", "unidiff"))

    sealed_dev_enabled = bool(sealed_dev_cfg.get("enabled", True))
    sealed_heldout_enabled = bool(sealed_heldout_cfg.get("enabled", False)) and heldout

    cdel_root = _resolve_path(base_dir, sealed_dev_cfg.get("cdel_root", "../CDEL-v2"))

    # Baseline calibration
    baseline_dir = os.path.join(run_dir, "baseline")
    os.makedirs(baseline_dir, exist_ok=True)
    baseline_results: List[Dict] = []

    if sealed_dev_enabled:
        for tier in ladder:
            if _check_run_timeout("sealed_dev"):
                break
            tier_dir = os.path.join(baseline_dir, f"tier_{tier['name']}")
            candidate = build_identity_candidate(
                repo_root=target_repo_path,
                base_commit=baseline_commit,
                target_repo_id=str(cfg.get("target_repo_id", "")),
                eval_plan_id=str(tier.get("sealed_dev_plan", "")),
                patch_format=patch_format,
                out_dir=tier_dir,
            )
            proof = _compute_apply_proof(
                repo_root=target_repo_path,
                base_commit=baseline_commit,
                patch_path=candidate["patch_path"],
                patch_text=candidate["patch_text"],
                candidate_id=candidate["candidate_id"],
                tmp_dir=os.path.join(tier_dir, "tmp"),
            )
            proof["semantic_noop"] = is_semantic_noop(candidate["patch_text"])
            _write_json(os.path.join(candidate["candidate_dir"], "candidate_apply_proof.json"), proof)

            result = run_sealed_eval(
                sealed_dev_cfg,
                candidate_tar=candidate["tar_path"],
                candidate_id=candidate["candidate_id"],
                cdel_root=cdel_root,
                repo_root=target_repo_path,
                out_dir=tier_dir,
                sealed_mode="baseline",
            )
            baseline_results.append(
                {
                    "tier": tier["name"],
                    "plan_id": tier.get("sealed_dev_plan", ""),
                    "status": result.get("status", "FAIL"),
                    "receipt_path": result.get("receipt_path", ""),
                }
            )
            if result.get("status") != "PASS":
                break
    else:
        if ladder:
            baseline_results.append(
                {
                    "tier": ladder[0]["name"],
                    "plan_id": ladder[0].get("sealed_dev_plan", ""),
                    "status": "FAIL",
                    "receipt_path": "",
                }
            )

    active_info = select_active_tier(ladder, baseline_results)
    curriculum_state = init_curriculum_state(active_info)

    active_idx = int(active_info.get("tier_index", 0))
    baseline_status = str(active_info.get("baseline_status", "FAIL"))
    baseline_result = baseline_results[active_idx] if active_idx < len(baseline_results) else {
        "tier": active_info.get("tier", ""),
        "plan_id": tier_info(ladder, curriculum_state).get("sealed_dev_plan", ""),
        "status": baseline_status,
        "receipt_path": "",
    }
    _write_json(os.path.join(baseline_dir, "baseline_sealed_dev_result.json"), baseline_result)
    if baseline_result.get("status") == "PASS":
        receipt_rel = str(baseline_result.get("receipt_path", ""))
        if receipt_rel:
            tier_dir = os.path.join(baseline_dir, f"tier_{baseline_result.get('tier','')}")
            receipt_src = os.path.join(tier_dir, receipt_rel)
            if os.path.exists(receipt_src):
                shutil.copyfile(receipt_src, os.path.join(baseline_dir, "receipt.json"))

    calibration = {"tiers": baseline_results, "active": active_info}
    _write_json(os.path.join(baseline_dir, "calibration.json"), calibration)

    baseline_status_by_tier = {entry.get("tier", ""): entry.get("status", "FAIL") for entry in baseline_results}

    seed = int(cfg.get("seed", 1))

    null_control_attempts = 0
    null_control_passes = 0
    noop_filtered_total = 0
    total_candidates = 0
    improvement_curve: List[Dict] = []
    rejections_total = {
        "APPLY_FAIL": 0,
        "SEMANTIC_NOOP": 0,
        "NO_PATCH_GENERATED": 0,
        "DEVSCREEN_ERROR": 0,
        "DEVSCREEN_SKIPPED": 0,
        "ELIGIBLE": 0,
    }
    operator_totals = {
        tid: {"attempted": 0, "applicable": 0, "produced_valid_patch": 0} for tid in template_pool
    }
    distance_improvement_total = 0

    if calibrate_only:
        epochs = 0

    for epoch in range(int(epochs)):
        if _check_run_timeout("epoch_start"):
            break

        tier = tier_info(ladder, curriculum_state)
        eval_plan_id = str(tier.get("sealed_dev_plan", ""))
        dev_cfg_epoch = dict(dev_cfg)
        dev_cfg_epoch["suite_id"] = str(tier.get("devscreen_suite", dev_cfg.get("suite_id", "")))
        dev_cfg_epoch.setdefault("max_evals_per_epoch", dev_cfg.get("max_evals_per_epoch", 0))

        epoch_dir = os.path.join(epochs_dir, f"epoch_{epoch:04d}")
        tmp_dir = os.path.join(epoch_dir, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        os.makedirs(os.path.join(epoch_dir, "devscreen"), exist_ok=True)
        os.makedirs(os.path.join(epoch_dir, "sealed_dev"), exist_ok=True)
        os.makedirs(os.path.join(epoch_dir, "sealed_heldout"), exist_ok=True)
        os.makedirs(os.path.join(epoch_dir, "candidates"), exist_ok=True)
        os.makedirs(os.path.join(epoch_dir, "controls"), exist_ok=True)

        epoch_started = time.monotonic()
        epoch_started_ms = int(epoch_started * 1000)
        epoch_summary_path = os.path.join(epoch_dir, "epoch_summary.json")
        _write_json_atomic(
            epoch_summary_path,
            {
                "epoch": int(epoch),
                "status": "STARTED",
                "started_at_monotonic": int(epoch_started_ms),
                "eligible_candidates": 0,
                "topk_submitted": 0,
                "sealed_passes": 0,
            },
        )

        partial = {
            "step": "",
            "candidates_generated": 0,
            "eligible_candidates": 0,
            "submitted": 0,
        }
        epoch_status = "COMPLETE"
        epoch_where = "none"

        try:
            def _check_epoch_timeout(where: str) -> None:
                if _check_run_timeout(where):
                    raise _EpochAbort(where)
                if epoch_wall_limit > 0 and time.monotonic() - epoch_started >= epoch_wall_limit:
                    timeout_info["status"] = "TIMEOUT"
                    timeout_info["where"] = where
                    raise _EpochAbort(where)

            partial["step"] = "baseline_devscreen"
            # Baseline devscreen for hints
            _check_epoch_timeout("devscreen")
            baseline_ws = os.path.join(tmp_dir, "baseline")
            create_workspace(target_repo_path, baseline_commit, baseline_ws)
            try:
                baseline_report = run_devscreen(dev_cfg_epoch, baseline_ws, seed, [])
            finally:
                remove_workspace(baseline_ws)

            _check_epoch_timeout("devscreen")
            baseline_distance = baseline_report.get("distance", {}) or {"failing_tests": 0, "errors": 0}
            baseline_payload = {
                "fail_signature": str(baseline_report.get("fail_signature", "")),
                "implicated_paths": list(baseline_report.get("implicated_paths", [])),
                "primary_exception": _primary_exception(str(baseline_report.get("normalized_log", ""))),
                "distance": baseline_distance,
            }
            _write_json(os.path.join(epoch_dir, "baseline_devscreen.json"), baseline_payload)

            baseline_hint = DevHint(
                implicated_paths=list(baseline_report.get("implicated_paths", [])),
                fail_signature=str(baseline_report.get("fail_signature", "")),
                normalized_error=str(baseline_report.get("normalized_log", "")),
            )

            # Null control
            null_control_pass = False
            null_control_id = ""
            if sealed_dev_enabled and eval_plan_id:
                _check_epoch_timeout("sealed_dev")
                control_dir = os.path.join(epoch_dir, "controls", "null_control")
                os.makedirs(control_dir, exist_ok=True)
                control_candidate = build_null_control_candidate(
                    repo_root=target_repo_path,
                    base_commit=baseline_commit,
                    target_repo_id=str(cfg.get("target_repo_id", "")),
                    eval_plan_id=eval_plan_id,
                    patch_format=patch_format,
                    out_dir=control_dir,
                )
                null_control_id = control_candidate["candidate_id"]
                proof = _compute_apply_proof(
                    repo_root=target_repo_path,
                    base_commit=baseline_commit,
                    patch_path=control_candidate["patch_path"],
                    patch_text=control_candidate["patch_text"],
                    candidate_id=control_candidate["candidate_id"],
                    tmp_dir=os.path.join(control_dir, "tmp"),
                )
                proof["semantic_noop"] = is_semantic_noop(control_candidate["patch_text"])
                _write_json(os.path.join(control_candidate["candidate_dir"], "candidate_apply_proof.json"), proof)

                result = run_sealed_eval(
                    sealed_dev_cfg,
                    candidate_tar=control_candidate["tar_path"],
                    candidate_id=control_candidate["candidate_id"],
                    cdel_root=cdel_root,
                    repo_root=target_repo_path,
                    out_dir=control_dir,
                    sealed_mode="null_control",
                )
                _write_json(os.path.join(epoch_dir, "controls", "null_control_sealed_dev_result.json"), result)
                null_control_pass = result.get("status") == "PASS"
            else:
                stub = _stub_sealed_result("", "null_control", "sealed_dev_disabled")
                _write_json(os.path.join(epoch_dir, "controls", "null_control_sealed_dev_result.json"), stub)

            if eval_plan_id:
                null_control_attempts += 1
                if null_control_pass:
                    null_control_passes += 1

            partial["step"] = "propose"
            candidate_records: List[Dict] = []
            eligible_pre_dev: List[Dict] = []
            noop_filtered = 0
            rejection_counts = {
                "APPLY_FAIL": 0,
                "SEMANTIC_NOOP": 0,
                "NO_PATCH_GENERATED": 0,
                "DEVSCREEN_ERROR": 0,
                "DEVSCREEN_SKIPPED": 0,
                "ELIGIBLE": 0,
            }
            operator_stats = {
                tid: {"attempted": 0, "applicable": 0, "produced_valid_patch": 0} for tid in template_pool
            }
            total_attempts = 0
            total_slots = 0
            seen_candidate_ids: set[str] = set()

            while total_attempts < max_total_attempts and (
                total_slots < candidates_per_epoch or len(eligible_pre_dev) < min_eligible_per_epoch
            ):
                _check_epoch_timeout("propose")
                rng = derive_rng(seed, epoch, total_slots)
                explore_num, explore_den = explore_fraction
                explore_pick = rng.randbelow(explore_den) < explore_num if explore_den > 0 else False
                sig_map = proposer_state.get("signature_to_templates", {}) or {}
                pref = [t for t in sig_map.get(baseline_hint.fail_signature, []) if t in template_pool]
                shuffled = _shuffle_templates(template_pool, rng)
                if explore_pick or not pref:
                    template_order = shuffled
                    mode = "explore"
                else:
                    template_order = pref + [t for t in shuffled if t not in pref]
                    mode = "exploit"

                slot_attempts = 0
                had_apply_fail = False
                had_semantic_noop = False
                slot_candidate = None
                chosen_template = ""

                while slot_attempts < max_attempts_per_slot and total_attempts < max_total_attempts:
                    if not template_order:
                        break
                    template_id = template_order[slot_attempts % len(template_order)]
                    chosen_template = template_id
                    slot_attempts += 1
                    total_attempts += 1
                    if template_id in operator_stats:
                        operator_stats[template_id]["attempted"] += 1

                    ws_dir = os.path.join(tmp_dir, f"ws_{total_slots:04d}_{slot_attempts:02d}")
                    create_workspace(target_repo_path, baseline_commit, ws_dir)
                    try:
                        template = get_template(template_id)
                        patch_text = template.apply(ws_dir, baseline_hint, rng)
                        if not patch_text:
                            continue
                        if template_id in operator_stats:
                            operator_stats[template_id]["applicable"] += 1
                        if max_patch_bytes and len(patch_text.encode("utf-8")) > max_patch_bytes:
                            continue

                        patch_bytes = patch_text.encode("utf-8")
                        manifest = build_manifest(
                            base_commit=baseline_commit,
                            eval_plan_id=eval_plan_id,
                            patch_bytes=patch_bytes,
                            target_repo_id=str(cfg.get("target_repo_id", "")),
                            patch_format=patch_format,
                        )
                        candidate_id = manifest["candidate_id"]
                        if candidate_id in seen_candidate_ids:
                            continue
                        cand_dir = os.path.join(epoch_dir, "candidates", candidate_id)
                        paths = _write_candidate_bundle(cand_dir, manifest, patch_bytes)

                        semantic_noop = is_semantic_noop(patch_text)
                        proof = _compute_apply_proof(
                            repo_root=target_repo_path,
                            base_commit=baseline_commit,
                            patch_path=paths["patch_path"],
                            patch_text=patch_text,
                            candidate_id=candidate_id,
                            tmp_dir=os.path.join(tmp_dir, f"apply_{total_slots:04d}_{slot_attempts:02d}"),
                        )
                        proof["semantic_noop"] = semantic_noop
                        _write_json(os.path.join(cand_dir, "candidate_apply_proof.json"), proof)

                        applies_cleanly = bool(proof.get("applies_cleanly"))
                        if not applies_cleanly:
                            had_apply_fail = True
                            shutil.rmtree(cand_dir, ignore_errors=True)
                            continue
                        if semantic_noop:
                            had_semantic_noop = True
                            shutil.rmtree(cand_dir, ignore_errors=True)
                            continue

                        if template_id in operator_stats:
                            operator_stats[template_id]["produced_valid_patch"] += 1

                        seen_candidate_ids.add(candidate_id)
                        slot_candidate = {
                            "candidate_id": candidate_id,
                            "template_id": template_id,
                            "mode": mode,
                            "devscreen": {},
                            "devscreen_ok": False,
                            "fail_signature": "",
                            "patch_path": paths["patch_path"],
                            "manifest_path": paths["manifest_path"],
                            "tar_path": paths["tar_path"],
                            "semantic_noop": False,
                            "applies_cleanly": True,
                            "eligible_for_sealed": False,
                            "distance": baseline_distance,
                            "patch_bytes": int(len(patch_bytes)),
                        }
                        break
                    finally:
                        remove_workspace(ws_dir)

                if slot_candidate:
                    candidate_records.append(slot_candidate)
                    eligible_pre_dev.append(slot_candidate)
                else:
                    candidate_id = _synthetic_candidate_id(seed, epoch, total_slots)
                    cand_dir = os.path.join(epoch_dir, "candidates", candidate_id)
                    os.makedirs(cand_dir, exist_ok=True)
                    reject_reason = "NO_PATCH_GENERATED"
                    if had_semantic_noop:
                        reject_reason = "SEMANTIC_NOOP"
                    elif had_apply_fail:
                        reject_reason = "APPLY_FAIL"
                    applies_cleanly = reject_reason == "SEMANTIC_NOOP"
                    filter_report = {
                        "candidate_id": candidate_id,
                        "applies_cleanly": applies_cleanly,
                        "semantic_noop": bool(had_semantic_noop),
                        "devscreen_ran": False,
                        "devscreen_ok": False,
                        "baseline_distance": baseline_distance,
                        "candidate_distance": baseline_distance,
                        "distance_delta": _distance_delta(baseline_distance, baseline_distance),
                        "eligible_for_sealed": False,
                        "reject_reason": reject_reason,
                    }
                    _write_json(os.path.join(cand_dir, "filter_report.json"), filter_report)
                    rejection_counts[reject_reason] += 1
                    if reject_reason == "SEMANTIC_NOOP":
                        noop_filtered += 1
                    candidate_records.append(
                        {
                            "candidate_id": candidate_id,
                            "template_id": chosen_template,
                            "mode": mode,
                            "devscreen": {},
                            "devscreen_ok": False,
                            "fail_signature": "",
                            "patch_path": "",
                            "manifest_path": "",
                            "tar_path": "",
                            "semantic_noop": bool(had_semantic_noop),
                            "applies_cleanly": applies_cleanly,
                            "eligible_for_sealed": False,
                            "distance": baseline_distance,
                            "patch_bytes": 0,
                        }
                    )

                total_slots += 1

            partial["candidates_generated"] = int(total_slots)
            total_candidates += total_slots
            noop_filtered_total += noop_filtered

            partial["step"] = "devscreen_eval"
            devscreen_limit = int(dev_cfg_epoch.get("max_evals_per_epoch", 0))
            selected_ids, selected_reasons = _select_devscreen_eval_set(eligible_pre_dev, devscreen_limit)
            selected_set = set(selected_ids)
            devscreen_eval_payload = {
                "max_evals_per_epoch": int(devscreen_limit),
                "selected": [
                    {"candidate_id": cid, "reason": selected_reasons.get(cid, "")}
                    for cid in selected_ids
                ],
            }
            _write_json(os.path.join(epoch_dir, "devscreen_eval_set.json"), devscreen_eval_payload)

            for rec in eligible_pre_dev:
                cid = rec.get("candidate_id", "")
                if not cid:
                    continue
                cand_dir = os.path.join(epoch_dir, "candidates", cid)
                if cid not in selected_set:
                    filter_report = {
                        "candidate_id": cid,
                        "applies_cleanly": True,
                        "semantic_noop": False,
                        "devscreen_ran": False,
                        "devscreen_ok": False,
                        "baseline_distance": baseline_distance,
                        "candidate_distance": baseline_distance,
                        "distance_delta": _distance_delta(baseline_distance, baseline_distance),
                        "eligible_for_sealed": False,
                        "reject_reason": "DEVSCREEN_SKIPPED",
                    }
                    _write_json(os.path.join(cand_dir, "filter_report.json"), filter_report)
                    rejection_counts["DEVSCREEN_SKIPPED"] += 1
                    rec["eligible_for_sealed"] = False
                    rec["devscreen_ok"] = False
                    rec["distance"] = baseline_distance
                    continue

                _check_epoch_timeout("devscreen")
                ws_dir = os.path.join(tmp_dir, f"dev_{cid[:8]}")
                create_workspace(target_repo_path, baseline_commit, ws_dir)
                devscreen_report = None
                try:
                    proc = subprocess.run(["git", "apply", rec.get("patch_path", "")], cwd=ws_dir, capture_output=True)
                    if proc.returncode == 0:
                        patch_path = rec.get("patch_path", "")
                        patch_text = ""
                        if patch_path:
                            with open(patch_path, "r", encoding="utf-8") as f:
                                patch_text = f.read()
                        implicated_paths = _extract_paths_from_patch(patch_text)
                        devscreen_report = run_devscreen(dev_cfg_epoch, ws_dir, seed, implicated_paths)
                except Exception:
                    devscreen_report = None
                finally:
                    remove_workspace(ws_dir)

                if not devscreen_report:
                    filter_report = {
                        "candidate_id": cid,
                        "applies_cleanly": True,
                        "semantic_noop": False,
                        "devscreen_ran": False,
                        "devscreen_ok": False,
                        "baseline_distance": baseline_distance,
                        "candidate_distance": baseline_distance,
                        "distance_delta": _distance_delta(baseline_distance, baseline_distance),
                        "eligible_for_sealed": False,
                        "reject_reason": "DEVSCREEN_ERROR",
                    }
                    _write_json(os.path.join(cand_dir, "filter_report.json"), filter_report)
                    rejection_counts["DEVSCREEN_ERROR"] += 1
                    rec["eligible_for_sealed"] = False
                    rec["devscreen_ok"] = False
                    rec["distance"] = baseline_distance
                    continue

                devscreen_report["candidate_id"] = cid
                devscreen_dir = os.path.join(epoch_dir, "devscreen", f"candidate_{cid}")
                _write_json(os.path.join(devscreen_dir, "devscreen.json"), devscreen_report)

                rec["devscreen"] = devscreen_report
                rec["devscreen_ok"] = bool(devscreen_report.get("ok"))
                rec["fail_signature"] = str(devscreen_report.get("fail_signature", ""))
                rec["eligible_for_sealed"] = True
                rec["distance"] = devscreen_report.get("distance", {}) or {"failing_tests": 0, "errors": 0}

                filter_report = {
                    "candidate_id": cid,
                    "applies_cleanly": True,
                    "semantic_noop": False,
                    "devscreen_ran": True,
                    "devscreen_ok": bool(devscreen_report.get("ok")),
                    "baseline_distance": baseline_distance,
                    "candidate_distance": rec["distance"],
                    "distance_delta": _distance_delta(baseline_distance, rec["distance"]),
                    "eligible_for_sealed": True,
                    "reject_reason": "NONE",
                }
                _write_json(os.path.join(cand_dir, "filter_report.json"), filter_report)
                rejection_counts["ELIGIBLE"] += 1

            rejections_payload = {"counts": rejection_counts}
            if total_attempts >= max_total_attempts and len(eligible_pre_dev) < min_eligible_per_epoch:
                rejections_payload["diagnosis"] = "max_total_attempts_exhausted"
            _write_json(os.path.join(epoch_dir, "rejections.json"), rejections_payload)
            _write_json(os.path.join(epoch_dir, "operator_applicability.json"), operator_stats)

            for key in rejection_counts:
                rejections_total[key] = int(rejections_total.get(key, 0)) + int(rejection_counts.get(key, 0))
            for tid, stats in operator_stats.items():
                agg = operator_totals.setdefault(tid, {"attempted": 0, "applicable": 0, "produced_valid_patch": 0})
                agg["attempted"] = int(agg.get("attempted", 0)) + int(stats.get("attempted", 0))
                agg["applicable"] = int(agg.get("applicable", 0)) + int(stats.get("applicable", 0))
                agg["produced_valid_patch"] = int(agg.get("produced_valid_patch", 0)) + int(
                    stats.get("produced_valid_patch", 0)
                )

            eligible_records = [r for r in candidate_records if r.get("candidate_id") and r.get("eligible_for_sealed")]
            partial["eligible_candidates"] = int(len(eligible_records))

            # De-duplicate by candidate_id to match on-disk filter_report (last write wins).
            eligible_map: Dict[str, Dict] = {}
            for rec in eligible_records:
                cid = str(rec.get("candidate_id", ""))
                if not cid:
                    continue
                if cid in eligible_map:
                    del eligible_map[cid]
                eligible_map[cid] = rec
            eligible_records = list(eligible_map.values())

            topk, ranked_all = select_topk_for_submission(eligible_records, baseline_distance, topk_to_sealed)
            topk_ids = [r.get("candidate_id", "") for r in topk if r.get("candidate_id")]
            ranked_ids = [r.get("candidate_id", "") for r in ranked_all if r.get("candidate_id")]
            best_delta = _distance_delta(
                baseline_distance, (ranked_all[0].get("distance", {}) if ranked_all else baseline_distance)
            )
            if any(
                _distance_delta(baseline_distance, r.get("distance", {})).get("failing_tests", 0) < 0
                or _distance_delta(baseline_distance, r.get("distance", {})).get("errors", 0) < 0
                for r in eligible_records
            ):
                distance_improvement_total += 1

            sealed_passes = 0
            sealed_heldout_passes = 0
            sealed_heldout_attempts = 0
            submitted = 0

            partial["step"] = "sealed_dev_submit"
            if sealed_dev_enabled:
                for rec in topk:
                    _check_epoch_timeout("sealed_dev")
                    cand_id = rec.get("candidate_id")
                    if not cand_id:
                        continue
                    out_dir = os.path.join(epoch_dir, "sealed_dev", f"candidate_{cand_id}")
                    result = run_sealed_eval(
                        sealed_dev_cfg,
                        candidate_tar=rec.get("tar_path"),
                        candidate_id=cand_id,
                        cdel_root=cdel_root,
                        repo_root=target_repo_path,
                        out_dir=out_dir,
                        sealed_mode="dev",
                    )
                    submitted += 1
                    partial["submitted"] = int(submitted)
                    if result.get("status") == "PASS":
                        sealed_passes += 1
                        rec["sealed_dev_pass"] = True
                    else:
                        rec["sealed_dev_pass"] = False

            partial["submitted"] = int(submitted)

            promotion_report = None
            if sealed_heldout_enabled:
                promotion_entries = []
                for rec in topk:
                    if not rec.get("sealed_dev_pass"):
                        continue
                    if rec.get("semantic_noop"):
                        continue
                    patch_path = rec.get("patch_path")
                    if not patch_path:
                        continue
                    with open(patch_path, "rb") as f:
                        patch_bytes = f.read()
                    held_manifest = build_manifest(
                        base_commit=baseline_commit,
                        eval_plan_id=str(sealed_heldout_cfg.get("eval_plan_id", "")),
                        patch_bytes=patch_bytes,
                        target_repo_id=str(cfg.get("target_repo_id", "")),
                        patch_format=patch_format,
                    )
                    held_id = held_manifest["candidate_id"]
                    held_dir = os.path.join(epoch_dir, "sealed_heldout", f"candidate_{held_id}")
                    os.makedirs(held_dir, exist_ok=True)
                    held_patch = os.path.join(held_dir, "patch.diff")
                    held_manifest_path = os.path.join(held_dir, "manifest.json")
                    held_tar = os.path.join(held_dir, "candidate.tar")
                    with open(held_patch, "wb") as f:
                        f.write(patch_bytes)
                    with open(held_manifest_path, "wb") as f:
                        f.write(canon_bytes(held_manifest))
                    write_deterministic_tar(held_tar, {"manifest.json": canon_bytes(held_manifest), "patch.diff": patch_bytes})
                    result = run_sealed_eval(
                        sealed_heldout_cfg,
                        candidate_tar=held_tar,
                        candidate_id=held_id,
                        cdel_root=cdel_root,
                        repo_root=target_repo_path,
                        out_dir=held_dir,
                        sealed_mode="heldout",
                    )
                    status = result.get("status")
                    receipt_rel = result.get("receipt_path", "")
                    promotion_entries.append(
                        {
                            "candidate_id": held_id,
                            "status": status,
                            "receipt_path": receipt_rel,
                        }
                    )
                    if status == "PASS":
                        sealed_heldout_passes += 1
                    sealed_heldout_attempts += 1
                promotion_report = {
                    "epoch": int(epoch),
                    "heldout_passes": int(sealed_heldout_passes),
                    "entries": promotion_entries,
                }
                _write_json(os.path.join(epoch_dir, "sealed_heldout", "promotion_report.json"), promotion_report)

            # Update proposer state
            baseline_failed = baseline_status_by_tier.get(str(tier.get("name", "")), "") == "FAIL"
            prior_count = len(proposer_state.get("improvement_events", []))
            update_state(
                proposer_state,
                epoch,
                candidate_records,
                baseline_failed=baseline_failed,
                tier_name=str(tier.get("name", "")),
            )
            save_state(state_path, proposer_state)

            improvements_all = proposer_state.get("improvement_events", [])
            new_events = improvements_all[prior_count:]
            template_credits: Dict[str, int] = {}
            for event in new_events:
                tid = str(event.get("template_id", ""))
                template_credits[tid] = template_credits.get(tid, 0) + 1

            improvement_curve.append(
                {
                    "epoch": int(epoch),
                    "sealed_submissions": int(len(topk_ids)),
                    "sealed_passes": int(sealed_passes),
                    "improvements": int(len(new_events)),
                    "best_distance_delta": best_delta,
                    "template_credits": template_credits,
                }
            )

            curriculum_state, curriculum_notes = update_curriculum_state(
                curriculum_cfg,
                ladder,
                curriculum_state,
                sealed_passes,
                len(topk_ids),
                null_control_pass,
            )

            # Top templates
            stats_items = list((proposer_state.get("template_stats") or {}).items())
            stats_items.sort(
                key=lambda item: (
                    -int(item[1].get("sealed_dev_passes", 0)),
                    -int(item[1].get("devscreen_passes", 0)),
                    -int(item[1].get("attempts", 0)),
                    str(item[0]),
                )
            )
            top_template_ids = [tid for tid, _ in stats_items[:3]]

            noop_fraction = _ratio(noop_filtered, max(1, total_slots))

            epoch_summary = {
                "epoch": int(epoch),
                "status": "COMPLETE",
                "where": "none",
                "baseline_commit": baseline_commit,
                "candidates_total": int(total_slots),
                "eligible_candidates": int(len(eligible_records)),
                "topk_submitted": int(len(topk_ids)),
                "sealed_passes": int(sealed_passes),
                "sealed_heldout_passes": int(sealed_heldout_passes),
                "best_candidate_id": topk_ids[0] if topk_ids else "",
                "curriculum": {"tier": str(tier.get("name", "")), "notes": curriculum_notes},
                "determinism": {"seed": int(seed), "rng_version": "pcg32_v1"},
                "topk_candidate_ids": topk_ids,
                "ranked_candidate_ids": ranked_ids,
                "best_distance_delta": best_delta,
                "top_template_ids": top_template_ids,
                "null_control_pass": bool(null_control_pass),
                "null_control_candidate_id": null_control_id,
                "noop_filtered": int(noop_filtered),
                "noop_filtered_fraction": noop_fraction,
                "improvement_events": int(len(new_events)),
            }
            _write_json_atomic(os.path.join(epoch_dir, "epoch_summary.json"), epoch_summary)

            costs = {
                "devscreen_runs": int(len(selected_ids)),
                "sealed_dev_runs": int(len(topk_ids)) if sealed_dev_enabled else 0,
                "sealed_heldout_runs": int(sealed_heldout_attempts) if sealed_heldout_enabled else 0,
            }
            update_scoreboard(scoreboard, epoch_summary, proposer_state.get("template_stats", {}), costs, int(curriculum_cfg.get("rolling_window", 5)))

        except _EpochAbort as exc:
            epoch_status = "INCOMPLETE"
            epoch_where = exc.where
        except Exception:
            epoch_status = "INCOMPLETE"
            epoch_where = "exception"
            timeout_info.setdefault("status", "ERROR")
            timeout_info["status"] = "ERROR"
            timeout_info["where"] = epoch_where
        finally:
            if epoch_status != "COMPLETE":
                incomplete_summary = {
                    "epoch": int(epoch),
                    "status": "INCOMPLETE",
                    "where": str(epoch_where),
                    "partial": partial,
                }
                _write_json_atomic(epoch_summary_path, incomplete_summary)

            shutil.rmtree(tmp_dir, ignore_errors=True)

        if epoch_status != "COMPLETE":
            break
    _write_json(os.path.join(run_dir, "scoreboard.json"), scoreboard)

    notes: List[str] = []
    if active_info.get("all_pass"):
        notes.append("baseline_pass_all_tiers")
    if active_info.get("all_fail"):
        notes.append("baseline_fail_all_tiers")
    total_sealed_passes = sum(int(e.get("sealed_passes", 0)) for e in improvement_curve)
    total_improvements = sum(int(e.get("improvements", 0)) for e in improvement_curve)
    sanity_status = timeout_info.get("status", "OK")
    if (
        sanity_status == "OK"
        and baseline_status == "FAIL"
        and total_sealed_passes == 0
        and total_improvements == 0
        and distance_improvement_total == 0
    ):
        sanity_status = "NO_SIGNAL_SEARCH_SPACE"
    sanity = {
        "baseline": {"tier": active_info.get("tier", ""), "status": baseline_status},
        "status": sanity_status,
        "where": timeout_info.get("where", ""),
        "null_control_pass_rate": _ratio(null_control_passes, max(1, null_control_attempts)),
        "noop_filtered_fraction": _ratio(noop_filtered_total, max(1, total_candidates)),
        "active_plan_id": tier_info(ladder, curriculum_state).get("sealed_dev_plan", ""),
        "notes": notes,
    }
    if sanity_status == "NO_SIGNAL_SEARCH_SPACE":
        sanity["rejections"] = rejections_total
        sanity["operator_applicability"] = operator_totals
    _write_json(os.path.join(run_dir, "sanity.json"), sanity)

    improvement_payload = {
        "schema_version": "flagship_code_rsi_v1_improvement_curve",
        "baseline": {"tier": active_info.get("tier", ""), "status": baseline_status},
        "epochs": improvement_curve,
    }
    _write_json(os.path.join(run_dir, "improvement_curve.json"), improvement_payload)

    return run_dir


__all__ = ["run_flagship", "resolve_baseline_commit", "build_identity_candidate"]
