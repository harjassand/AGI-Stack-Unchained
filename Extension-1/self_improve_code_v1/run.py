"""Run orchestrator for self_improve_code_v1 (RE3+++)."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
from typing import Dict, List, Tuple

from .canon.json_canon_v1 import canon_bytes
from .canon.hash_v1 import sha256_hex, sha256_bytes
from .canon.jsonl_v1 import HISTORY_SEED_HEX
from .package.candidate_hash_v1 import set_candidate_id_backend
from .state.schema_state_v1 import make_state
from .state.state_io_v1 import load_state, save_state
from .state.state_update_v1 import apply_attempt
from .state.attempt_log_v1 import append_attempt
from .targets.load_arms_v1 import load_arms
from .ops.token_locator_v1 import locate_token_span, TokenLocationError
from .ops.token_edit_v1 import read_text_normalized, write_text_lf
from .ops.compose_v1 import Edit, compose_edits, apply_edits
from .patch.unified_diff_v1 import unified_diff
from .patch.patch_stats_v1 import patch_stats
from .package.manifest_v1 import build_manifest
from .package.tar_deterministic_v1 import write_deterministic_tar
from .search.schedule_v1 import schedule_candidates
from .search.reward_v1 import compute_reward
from .devscreen.workspace_v1 import create_workspace, remove_workspace
from .devscreen.run_devscreen_v1 import run_devscreen
from .cdel.submit_v1 import run_cdel, discover_evidence, copy_stub_outputs
from .run_manifest_v1 import build_run_manifest, rank_attempts


def _resolve_relpath(base_dir: str, path: str) -> str:
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base_dir, path))


def _format_argv(argv: List[str], mapping: Dict[str, str]) -> List[str]:
    out: List[str] = []
    for arg in argv:
        new = arg
        for k, v in mapping.items():
            new = new.replace("{" + k + "}", v)
        out.append(new)
    return out


def _rewrite_repo_paths(argv: List[str], repo_root: str, repo_id: str, workspace_dir: str, run_config_dir: str) -> List[str]:
    out: List[str] = []
    repo_root_abs = os.path.abspath(repo_root)
    repo_base = os.path.basename(repo_root_abs)
    for arg in argv:
        new = arg
        # Resolve script paths relative to run_config_dir
        if new.endswith(".py") and not os.path.isabs(new):
            cand = _resolve_relpath(run_config_dir, new)
            if os.path.exists(cand):
                new = cand
        # Map absolute paths under repo_root to workspace
        if os.path.isabs(new) and new.startswith(repo_root_abs + os.sep):
            rel = os.path.relpath(new, repo_root_abs)
            new = os.path.join(workspace_dir, rel)
        # Strip repo_id/ or repo_base/ prefix if file exists in workspace
        for prefix in (repo_id + "/", repo_base + "/"):
            if new.startswith(prefix):
                stripped = new[len(prefix) :]
                if os.path.exists(os.path.join(workspace_dir, stripped)):
                    new = stripped
                    break
        out.append(new)
    return out


def _normalize_cwd(cwd_cfg: str, run_config_dir: str, workspace_dir: str, repo_root: str) -> str:
    if not cwd_cfg or cwd_cfg == ".":
        return workspace_dir
    if os.path.isabs(cwd_cfg):
        cwd_abs = cwd_cfg
    else:
        cwd_abs = _resolve_relpath(run_config_dir, cwd_cfg)
    if os.path.abspath(cwd_abs) == os.path.abspath(repo_root):
        cwd_abs = workspace_dir
    # If still outside workspace, treat as workspace-relative
    if not os.path.abspath(cwd_abs).startswith(os.path.abspath(workspace_dir)):
        cwd_abs = os.path.abspath(os.path.join(workspace_dir, cwd_cfg))
    if not os.path.abspath(cwd_abs).startswith(os.path.abspath(workspace_dir)):
        raise RuntimeError("devscreen cwd resolves outside workspace")
    return cwd_abs


def _normalize_run_config(run_config: Dict, run_config_dir: str, overrides: Dict) -> Dict:
    cfg = dict(run_config)
    cfg.setdefault("format", "self_improve_code_run_config_v1")
    cfg.setdefault("schema_version", "1")
    cfg.setdefault("search", {})

    # Seed override
    if overrides.get("seed") is not None:
        cfg["seed"] = overrides["seed"]
    cfg.setdefault("seed", 0)

    # target_repo mapping
    target_repo = dict(cfg.get("target_repo", {}))
    if not target_repo:
        # Back-compat: old keys
        target_repo = {
            "repo_id": os.path.basename(cfg.get("repo_path", "")) or "repo",
            "repo_root": cfg.get("repo_path", ""),
            "baseline_commit": cfg.get("baseline_commit", ""),
        }
    if not target_repo.get("repo_id"):
        target_repo["repo_id"] = os.path.basename(target_repo.get("repo_root", "")) or "repo"

    # Baseline override
    if overrides.get("baseline_commit"):
        target_repo["baseline_commit"] = overrides["baseline_commit"]
    if not target_repo.get("baseline_commit"):
        raise SystemExit("run_config missing baseline_commit")

    target_repo["repo_root"] = _resolve_relpath(run_config_dir, target_repo.get("repo_root", ""))
    if not target_repo.get("repo_root"):
        raise SystemExit("run_config missing target_repo.repo_root")
    cfg["target_repo"] = target_repo

    # eval_plan_id override
    eval_plan_id = overrides.get("eval_plan_id") or cfg.get("eval_plan_id")
    if not eval_plan_id:
        eval_plan_id = cfg.get("target_repo", {}).get("eval_plan_id", "")
    if not eval_plan_id:
        raise SystemExit("run_config missing eval_plan_id")
    cfg["eval_plan_id"] = eval_plan_id

    # workspace
    workspace = dict(cfg.get("workspace", {}))
    workspace.setdefault("materialize", "git_archive_v1")
    workspace_root = workspace.get("repo_root", target_repo.get("repo_root", ""))
    workspace["repo_root"] = _resolve_relpath(run_config_dir, workspace_root)
    cfg["workspace"] = workspace

    # arms_file
    if not cfg.get("arms_file"):
        cfg["arms_file"] = "self_improve_code_v1/targets/arms_v1.json"

    # devscreen
    dev = dict(cfg.get("devscreen", {}))
    dev.setdefault("argv", dev.get("devscreen_argv", []))
    dev.setdefault("cwd", dev.get("devscreen_cwd_rel", "."))
    dev.setdefault("env", dev.get("devscreen_env", {}))
    metric = dict(dev.get("metric", {})) if isinstance(dev.get("metric", {}), dict) else {}
    if dev.get("metric_file_relpath"):
        metric.setdefault("file_relpath", dev.get("metric_file_relpath"))
    if dev.get("metric_json_pointer"):
        metric.setdefault("json_pointer", dev.get("metric_json_pointer"))
    dev["metric"] = metric
    dev.setdefault("denylist_tokens", [])
    dev.setdefault("fastcheck_py_compile", True)
    cfg["devscreen"] = dev

    # cdel
    cdel = dict(cfg.get("cdel", {}))
    cdel.setdefault("backend", "cli_v1")
    cdel.setdefault("argv", cdel.get("cdel_argv", []))
    cdel.setdefault("cwd", cdel.get("cdel_cwd_rel", "."))
    cdel.setdefault("env", cdel.get("cdel_env", {}))
    cfg["cdel"] = cdel

    # candidate_id
    candidate_id = dict(cfg.get("candidate_id", {}))
    if not candidate_id:
        candidate_id = {"backend": "re2_authoritative_fail_closed_v1"}
    # resolve pythonpath_add to absolute paths
    if candidate_id.get("pythonpath_add"):
        abs_paths = []
        for p in candidate_id.get("pythonpath_add", []):
            abs_paths.append(_resolve_relpath(run_config_dir, p))
        candidate_id["pythonpath_add"] = abs_paths
    cfg["candidate_id"] = candidate_id

    # search defaults
    search = dict(cfg.get("search", {}))
    search.setdefault("budget_candidates", 0)
    search.setdefault("max_edit_set_size", 1)
    search.setdefault("max_token_spans_per_file", 1)
    search.setdefault("bonus0", 0)
    search.setdefault("beta", 0)
    search.setdefault("eta", 1)
    search.setdefault("A", 1)
    search.setdefault("B1", 0)
    search.setdefault("B2", 0)
    search.setdefault("R", 1000000)
    cfg["search"] = search

    # outputs
    expected = list(cfg.get("expected_output_relpaths", []))
    if not expected:
        expected = [
            "run_config.json",
            "state_before.json",
            "state_after.json",
            "attempts.jsonl",
            "baseline_report.json",
            "topk/",
            "selected/",
            "run_manifest.json",
            "verify_run.py",
        ]
    cfg["expected_output_relpaths"] = expected

    return cfg


def _run_id(run_config: Dict, state_before: Dict) -> str:
    rc_hash = sha256_bytes(canon_bytes(run_config))
    st_hash = sha256_bytes(canon_bytes(state_before))
    return sha256_hex(b"re3_run_v1\x00" + rc_hash + st_hash)


def _literal_type(lit: str) -> str:
    if lit.lower() in {"true", "false"}:
        return "bool"
    if lit.startswith("-"):
        num = lit[1:]
    else:
        num = lit
    if num.isdigit():
        return "int"
    if len(lit) >= 2 and lit[0] == lit[-1] and lit[0] in {"'", '"'}:
        return "string"
    if any(ch in lit for ch in "[](),"):
        return "table"
    return "other"


def _validate_literal(op_type: str, current: str, new_value: str) -> str:
    cur_type = _literal_type(current)
    if op_type == "set_int_literal_v1":
        if cur_type != "int":
            raise ValueError("current literal not int")
        if _literal_type(new_value) != "int":
            raise ValueError("new literal not int")
        return new_value
    if op_type == "set_bool_literal_v1":
        if cur_type != "bool":
            raise ValueError("current literal not bool")
        if new_value.lower() not in {"true", "false"}:
            raise ValueError("new literal not bool")
        if current in {"True", "False"}:
            return "True" if new_value.lower() == "true" else "False"
        if current in {"true", "false"}:
            return new_value.lower()
        return new_value
    if op_type == "set_string_enum_v1":
        if cur_type != "string":
            raise ValueError("current literal not string")
        if len(new_value) >= 2 and new_value[0] == new_value[-1] and new_value[0] in {"'", '"'}:
            return new_value
        quote = current[0]
        return f"{quote}{new_value}{quote}"
    if op_type in {"set_small_int_table_v1", "set_weight_vector_v1"}:
        if any(ch in new_value for ch in [".", "e", "E"]):
            raise ValueError("floats not allowed")
        return new_value
    raise ValueError("unknown op_type")


def _apply_candidate(
    workspace_dir: str,
    arms_by_id: Dict[str, Dict],
    arm_ids: List[str],
    value_choices: List[str],
    max_spans_per_file: int,
) -> Tuple[Dict[str, str], Dict[str, str], List[str]]:
    edits: List[Edit] = []
    edited_files: List[str] = []
    original_contents: Dict[str, str] = {}

    for arm_id, value_choice in zip(arm_ids, value_choices):
        arm = arms_by_id[arm_id]
        relpath = arm["file_relpath"]
        file_path = os.path.join(workspace_dir, relpath)
        if relpath not in original_contents:
            original_contents[relpath] = read_text_normalized(file_path)
        content = original_contents[relpath]
        try:
            span = locate_token_span(content, arm["selector"])
        except TokenLocationError as e:
            raise ValueError(str(e))
        current_lit = content[span[0] : span[1]]
        if arm["op_type"] == "set_bool_literal_v1":
            value_set_lower = {v.lower() for v in arm["value_set"]}
            if current_lit.lower() not in value_set_lower:
                raise ValueError("current literal not in value_set")
            if value_choice.lower() not in value_set_lower:
                raise ValueError("value_choice not in value_set")
        elif arm["op_type"] == "set_string_enum_v1":
            cur_val = current_lit
            if len(cur_val) >= 2 and cur_val[0] == cur_val[-1] and cur_val[0] in {"'", '"'}:
                cur_val = cur_val[1:-1]
            if cur_val not in arm["value_set"]:
                raise ValueError("current literal not in value_set")
        else:
            if current_lit not in arm["value_set"]:
                raise ValueError("current literal not in value_set")
        if value_choice == current_lit:
            raise ValueError("no-op value choice")
        replacement = _validate_literal(arm["op_type"], current_lit, value_choice)
        if replacement == current_lit:
            raise ValueError("no-op value choice")
        delta_bytes = len(replacement) - len(current_lit)
        delta_lines = replacement.count("\n") - current_lit.count("\n")
        constraints = arm.get("constraints", {})
        max_bytes = int(constraints.get("max_bytes_delta", 0))
        max_lines = int(constraints.get("max_lines_delta", 0))
        if abs(delta_bytes) > max_bytes:
            raise ValueError("max_bytes_delta exceeded")
        if abs(delta_lines) > max_lines:
            raise ValueError("max_lines_delta exceeded")
        edits.append(Edit(relpath, span[0], span[1], replacement))

    by_file = compose_edits(edits, max_spans_per_file)
    if len(by_file.keys()) > 2:
        raise ValueError("too many files edited")

    changed_contents: Dict[str, str] = {}
    for relpath, file_edits in by_file.items():
        original = original_contents[relpath]
        updated = apply_edits(original, file_edits)
        changed_contents[relpath] = updated
        abs_path = os.path.join(workspace_dir, relpath)
        write_text_lf(abs_path, updated)
        edited_files.append(abs_path)
    return original_contents, changed_contents, edited_files


def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-config", required=False)
    parser.add_argument("--run_config", dest="run_config", required=False)
    parser.add_argument("--state", required=False)
    parser.add_argument("--output-root", required=False)
    parser.add_argument("--seed", type=int, required=False)
    parser.add_argument("--baseline-commit", required=False)
    parser.add_argument("--baseline_commit", dest="baseline_commit", required=False)
    parser.add_argument("--eval-plan-id", required=False)
    parser.add_argument("--eval_plan_id", dest="eval_plan_id", required=False)
    args = parser.parse_args()
    if not args.run_config:
        raise SystemExit("--run-config is required")

    with open(args.run_config, "rb") as f:
        run_config_in = json.loads(f.read().decode("utf-8"))

    run_config_dir = os.path.dirname(os.path.abspath(args.run_config))
    overrides = {
        "seed": args.seed,
        "baseline_commit": args.baseline_commit,
        "eval_plan_id": args.eval_plan_id,
    }
    run_config = _normalize_run_config(run_config_in, run_config_dir, overrides)

    # candidate_id backend must be set before packaging
    set_candidate_id_backend(run_config.get("candidate_id", {}), base_dir=run_config_dir)

    arms_path = run_config.get("arms_file")
    if not arms_path:
        raise SystemExit("run_config missing arms_file")
    if not os.path.isabs(arms_path):
        arms_path = os.path.join(run_config_dir, arms_path)
    if not os.path.exists(arms_path):
        alt1 = os.path.join(run_config_dir, "self_improve_code_v1", "targets", "arms_v1.json")
        alt2 = os.path.join(os.path.dirname(run_config_dir), "self_improve_code_v1", "targets", "arms_v1.json")
        if os.path.exists(alt1):
            arms_path = alt1
        elif os.path.exists(alt2):
            arms_path = alt2
        else:
            raise SystemExit("arms_file not found")
    arms = load_arms(arms_path)
    arm_ids = [a["arm_id"] for a in arms]
    arms_by_id = {a["arm_id"]: a for a in arms}

    if args.state:
        state_before = load_state(args.state)
    else:
        state_before = make_state(arm_ids)

    state_after = copy.deepcopy(state_before)

    run_id = _run_id(run_config, state_before)

    output_root = args.output_root
    if not output_root:
        output_root = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "runs", "self_improve_code_v1"
        )
    output_root = os.path.abspath(output_root)
    run_dir = os.path.join(output_root, run_id)
    os.makedirs(run_dir, exist_ok=False)
    os.makedirs(os.path.join(run_dir, "topk"), exist_ok=True)
    os.makedirs(os.path.join(run_dir, "selected"), exist_ok=True)
    tmp_dir = os.path.join(run_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    # Write run_config and state_before
    with open(os.path.join(run_dir, "run_config.json"), "wb") as f:
        f.write(canon_bytes(run_config))
    save_state(os.path.join(run_dir, "state_before.json"), state_before)

    attempts_path = os.path.join(run_dir, "attempts.jsonl")
    open(attempts_path, "wb").close()
    history_digest = HISTORY_SEED_HEX

    target_repo = run_config["target_repo"]
    repo_root = target_repo["repo_root"]
    repo_id = target_repo.get("repo_id", os.path.basename(repo_root))
    baseline_commit = target_repo["baseline_commit"]
    eval_plan_id = run_config["eval_plan_id"]
    seed = int(run_config.get("seed", 0))

    workspace_cfg = run_config.get("workspace", {})
    if workspace_cfg.get("materialize") != "git_archive_v1":
        raise SystemExit("unsupported workspace materialize mode")
    workspace_root = workspace_cfg.get("repo_root", repo_root)

    # Baseline devscreen
    baseline_ws = os.path.join(tmp_dir, "ws_baseline")
    create_workspace(workspace_root, baseline_commit, baseline_ws)
    try:
        empty_patch = os.path.join(tmp_dir, "baseline.patch")
        empty_tar = os.path.join(tmp_dir, "baseline.tar")
        open(empty_patch, "wb").close()
        open(empty_tar, "wb").close()

        out_dir = os.path.join(baseline_ws, "_devscreen_out")
        os.makedirs(out_dir, exist_ok=True)
        dev_cfg = run_config["devscreen"]
        argv = _format_argv(dev_cfg.get("argv", []), {"seed": str(seed), "out_dir": out_dir})
        argv = _rewrite_repo_paths(argv, repo_root, repo_id, baseline_ws, run_config_dir)
        cwd = _normalize_cwd(dev_cfg.get("cwd", "."), run_config_dir, baseline_ws, repo_root)
        devscreen_cfg = {
            "argv": argv,
            "cwd": cwd,
            "env": dev_cfg.get("env", {}),
            "metric": dev_cfg.get("metric", {}),
            "metric_alt_dirs": [out_dir],
            "denylist_tokens": dev_cfg.get("denylist_tokens", []),
            "fastcheck_py_compile": dev_cfg.get("fastcheck_py_compile", True),
        }
        baseline_report = run_devscreen(
            devscreen_cfg,
            baseline_ws,
            [],
            0,
            empty_patch,
            empty_tar,
        )
        baseline_report["baseline_m_bp"] = baseline_report["m_bp"]
    finally:
        remove_workspace(baseline_ws)

    with open(os.path.join(run_dir, "baseline_report.json"), "wb") as f:
        f.write(canon_bytes(baseline_report))

    m0_bp = int(baseline_report.get("m_bp", 0))

    # Schedule candidates
    candidates = schedule_candidates(
        arms,
        state_before,
        baseline_commit,
        eval_plan_id,
        {
            "bonus0": run_config["search"]["bonus0"],
            "beta": run_config["search"]["beta"],
            "max_edit_set_size": run_config["search"]["max_edit_set_size"],
            "budget_candidates": run_config["search"]["budget_candidates"],
        },
    )

    attempts: List[Dict] = []
    candidate_artifacts: Dict[str, Dict] = {}

    for idx, cand in enumerate(candidates, start=1):
        arm_ids = cand["arm_ids"]
        value_choices = cand["value_choices"]
        ws_dir = os.path.join(tmp_dir, f"ws_{idx}")
        status = "OK"
        candidate_id = ""
        patch_path = os.path.join(tmp_dir, f"cand_{idx}.diff")
        manifest_path = os.path.join(tmp_dir, f"cand_{idx}.manifest.json")
        tar_path = os.path.join(tmp_dir, f"cand_{idx}.tar")
        try:
            create_workspace(workspace_root, baseline_commit, ws_dir)
            original_contents, changed_contents, edited_files = _apply_candidate(
                ws_dir,
                arms_by_id,
                arm_ids,
                value_choices,
                int(run_config["search"]["max_token_spans_per_file"]),
            )
            if not changed_contents:
                raise ValueError("no changes")

            changes = {relpath: (original_contents[relpath], changed_contents[relpath]) for relpath in changed_contents}
            patch_text = unified_diff(changes)
            if not patch_text:
                raise ValueError("no diff")

            stats = patch_stats(patch_text)
            manifest = build_manifest(baseline_commit, eval_plan_id, patch_text, stats)
            candidate_id = manifest["candidate_id"]

            patch_bytes = patch_text.encode("utf-8")
            with open(patch_path, "wb") as f:
                f.write(patch_bytes)
            with open(manifest_path, "wb") as f:
                f.write(canon_bytes(manifest))
            write_deterministic_tar(
                tar_path,
                {"manifest.json": canon_bytes(manifest), "patch.diff": patch_bytes},
            )

            out_dir = os.path.join(ws_dir, "_devscreen_out")
            os.makedirs(out_dir, exist_ok=True)
            dev_cfg = run_config["devscreen"]
            argv = _format_argv(dev_cfg.get("argv", []), {"seed": str(seed), "out_dir": out_dir})
            argv = _rewrite_repo_paths(argv, repo_root, repo_id, ws_dir, run_config_dir)
            cwd = _normalize_cwd(dev_cfg.get("cwd", "."), run_config_dir, ws_dir, repo_root)
            devscreen_cfg = {
                "argv": argv,
                "cwd": cwd,
                "env": dev_cfg.get("env", {}),
                "metric": dev_cfg.get("metric", {}),
                "metric_alt_dirs": [out_dir],
                "denylist_tokens": dev_cfg.get("denylist_tokens", []),
                "fastcheck_py_compile": dev_cfg.get("fastcheck_py_compile", True),
            }
            devscreen_report = run_devscreen(
                devscreen_cfg,
                ws_dir,
                edited_files,
                m0_bp,
                patch_path,
                tar_path,
            )
            status = devscreen_report.get("status", "OK")
            costs = {
                "patch_bytes": stats["patch_bytes"],
                "test_runs": int(devscreen_report.get("costs", {}).get("test_runs", 0)),
            }
            reward = compute_reward(int(devscreen_report.get("m_bp", 0)), m0_bp, costs, run_config["search"])

            tar_sha = sha256_hex(open(tar_path, "rb").read())
            attempt = {
                "attempt_index": idx,
                "arm_ids": arm_ids,
                "value_choices": value_choices,
                "status": status,
                "m_bp": int(devscreen_report.get("m_bp", 0)),
                "baseline_m_bp": m0_bp,
                "reward": reward,
                "candidate_id": candidate_id,
                "patch_sha256": manifest["patch"]["sha256"],
                "patch_bytes": stats["patch_bytes"],
                "tar_sha256": tar_sha,
            }
            history_digest = append_attempt(attempts_path, attempt, history_digest)
            apply_attempt(state_after, attempt, int(run_config["search"]["eta"]))
            attempts.append(attempt)

            candidate_artifacts[candidate_id] = {
                "patch_path": patch_path,
                "manifest_path": manifest_path,
                "tar_path": tar_path,
                "devscreen_report": devscreen_report,
                "patch_sha256": manifest["patch"]["sha256"],
                "tar_sha256": tar_sha,
            }
        except Exception:
            status = "INVALID_ARM"
            attempt = {
                "attempt_index": idx,
                "arm_ids": arm_ids,
                "value_choices": value_choices,
                "status": status,
                "m_bp": 0,
                "baseline_m_bp": m0_bp,
                "reward": compute_reward(0, m0_bp, {"patch_bytes": 0}, run_config["search"]),
                "candidate_id": "",
                "patch_sha256": "",
            }
            history_digest = append_attempt(attempts_path, attempt, history_digest)
            apply_attempt(state_after, attempt, int(run_config["search"]["eta"]))
            attempts.append(attempt)
        finally:
            remove_workspace(ws_dir)

    # Write state_after
    save_state(os.path.join(run_dir, "state_after.json"), state_after)

    # Rank and select
    ranked = rank_attempts(attempts)
    topk_n = int(run_config.get("topk", 1))
    topk = ranked[:topk_n]

    # Write topk artifacts
    for rank_idx, attempt in enumerate(topk, start=1):
        cand_id = attempt.get("candidate_id", "")
        art = candidate_artifacts.get(cand_id)
        if not art:
            continue
        prefix = str(rank_idx)
        shutil.copyfile(art["patch_path"], os.path.join(run_dir, "topk", f"{prefix}_patch.diff"))
        shutil.copyfile(art["manifest_path"], os.path.join(run_dir, "topk", f"{prefix}_manifest.json"))
        shutil.copyfile(art["tar_path"], os.path.join(run_dir, "topk", f"{prefix}_candidate.tar"))
        with open(os.path.join(run_dir, "topk", f"{prefix}_devscreen_report.json"), "wb") as f:
            f.write(canon_bytes(art["devscreen_report"]))

    selected_candidate_id = topk[0].get("candidate_id") if topk else ""
    if selected_candidate_id:
        art = candidate_artifacts.get(selected_candidate_id)
        if art:
            shutil.copyfile(art["tar_path"], os.path.join(run_dir, "selected", "selected_candidate.tar"))
            with open(os.path.join(run_dir, "selected", "selected_devscreen_report.json"), "wb") as f:
                f.write(canon_bytes(art["devscreen_report"]))

            # Submit to CDEL
            cdel_out_dir = os.path.join(run_dir, "selected", "cdel_out")
            cdel_invoke, used_out_dir = run_cdel(
                run_config["cdel"],
                os.path.join(run_dir, "selected", "selected_candidate.tar"),
                run_config_dir,
                cdel_out_dir,
            )
            with open(os.path.join(run_dir, "selected", "cdel_invoke.json"), "wb") as f:
                f.write(canon_bytes(cdel_invoke))

            if run_config["cdel"].get("backend") == "stub_v1":
                discovery = copy_stub_outputs(used_out_dir, os.path.join(run_dir, "selected"))
            else:
                repo_root = target_repo.get("repo_root", os.path.abspath(os.path.join(workspace_root, "..")))
                discovery = discover_evidence(repo_root, selected_candidate_id, os.path.join(run_dir, "selected"))

            if discovery.get("cdel_discovery_status") == "NOT_FOUND":
                with open(os.path.join(run_dir, "selected", "cdel_result_report.json"), "wb") as f:
                    f.write(canon_bytes({"status": "NOT_FOUND"}))

    # run_manifest
    state_before_sha = sha256_hex(canon_bytes(load_state(os.path.join(run_dir, "state_before.json"))))
    state_after_sha = sha256_hex(canon_bytes(load_state(os.path.join(run_dir, "state_after.json"))))
    artifacts_digest = {}
    for cand_id, art in candidate_artifacts.items():
        artifacts_digest[cand_id] = {
            "patch_sha256": art.get("patch_sha256", ""),
            "tar_sha256": art.get("tar_sha256", ""),
        }
    manifest = build_run_manifest(run_config, attempts, state_before_sha, state_after_sha, artifacts_digest, selected_candidate_id)
    with open(os.path.join(run_dir, "run_manifest.json"), "wb") as f:
        f.write(canon_bytes(manifest))

    # verify_run.py
    verify_path = os.path.join(run_dir, "verify_run.py")
    with open(verify_path, "w", encoding="utf-8") as f:
        f.write(
            "import os, sys\n"
            "RUN_DIR = os.path.dirname(os.path.abspath(__file__))\n"
            "EXT_DIR = os.path.abspath(os.path.join(RUN_DIR, '..', '..', '..'))\n"
            "sys.path.insert(0, EXT_DIR)\n"
            "from self_improve_code_v1.verify.verify_run_v1 import verify_run\n"
            "ok, errors = verify_run(RUN_DIR)\n"
            "print('OK' if ok else 'FAIL')\n"
            "if errors:\n"
            "    for e in errors:\n"
            "        print(e)\n"
        )

    # Cleanup temp
    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    run()
