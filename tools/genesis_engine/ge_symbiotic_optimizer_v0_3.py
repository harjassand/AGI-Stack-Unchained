#!/usr/bin/env python3
"""SH-1 Genesis Engine symbiotic optimizer (receipt-driven, v0.3)."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
for candidate in (REPO_ROOT, REPO_ROOT / "CDEL-v2"):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

from cdel.v1_7r.canon import canon_bytes, write_canon_json
from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins
from cdel.v18_0.ccap_runtime_v1 import ccap_payload_id, compute_repo_base_tree_id
from cdel.v18_0.omega_common_v1 import canon_hash_obj, rat_q32, validate_schema
from cdel.v18_0.patch_diff_v1 import build_unified_patch_bytes

from tools.genesis_engine.sh1_pd_v1 import build_pd_from_patch_bytes, touched_paths_hash_for_paths, touched_paths_hash_prefix_hex
from tools.genesis_engine.sh1_xs_v1 import build_xs_snapshot, load_ge_config


_Q32_ONE = 1 << 32
_BUDGET_HINT_STEP_Q32 = 1 << 30
_BUDGET_HINT_MIN_Q32 = 1 << 30
_BUDGET_HINT_MAX_Q32 = 1 << 34
_SUPPORTED_TEMPLATE_IDS = {
    "COMMENT_APPEND",
    "CODE_FASTPATH_GUARD",
    "JSON_TWEAK_COOLDOWN",
    "JSON_TWEAK_COOLDOWN_MINUS_1",
    "JSON_TWEAK_BUDGET_HINT",
    "JSON_TWEAK_BUDGET_HINT_MINUS_1STEP",
}
_CODE_FASTPATH_TARGET_RELPATH = "orchestrator/common/run_invoker_v1.py"
_SPEEDUP_TARGET_RELPATHS = {
    "orchestrator/common/run_invoker_v1.py",
    "orchestrator/omega_v18_0/coordinator_v1.py",
    "orchestrator/omega_v18_0/decider_v1.py",
}
_MODEL_GENESIS_TARGET_HINT = "model_genesis"
_LLM_REPLAY_SCHEMA_VERSION = "orch_llm_replay_row_v1"


class _LLMReplayMissError(RuntimeError):
    pass


def _invalid(reason: str) -> RuntimeError:
    msg = reason
    if not msg.startswith("INVALID:"):
        msg = f"INVALID:{msg}"
    return RuntimeError(msg)


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _normalize_relpath(path_value: str) -> str:
    rel = str(path_value).strip().replace("\\", "/")
    path = Path(rel)
    if not rel or path.is_absolute() or ".." in path.parts:
        raise _invalid("SCHEMA_FAIL")
    return rel


def _load_active_ek(repo_root: Path, ek_id: str) -> dict[str, Any]:
    kernels_dir = repo_root / "authority" / "evaluation_kernels"
    for path in sorted(kernels_dir.glob("*.json"), key=lambda row: row.as_posix()):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != "evaluation_kernel_v1":
            continue
        if canon_hash_obj(payload) == ek_id:
            validate_schema(payload, "evaluation_kernel_v1")
            return payload
    raise _invalid("MISSING_STATE_INPUT")


def _load_build_recipes(repo_root: Path) -> list[dict[str, Any]]:
    payload = json.loads((repo_root / "authority" / "build_recipes" / "build_recipes_v1.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "build_recipes_v1":
        raise _invalid("SCHEMA_FAIL")
    rows = payload.get("recipes")
    if not isinstance(rows, list):
        raise _invalid("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(row)
    if not out:
        raise _invalid("MISSING_STATE_INPUT")
    return out


def _resolve_default_recipe_id(recipes: list[dict[str, Any]]) -> str:
    for row in recipes:
        if str(row.get("recipe_name", "")).strip() == "REPO_TESTS_FAST":
            value = str(row.get("recipe_id", "")).strip()
            if value.startswith("sha256:"):
                return value
            raise _invalid("SCHEMA_FAIL")
    value = str(recipes[0].get("recipe_id", "")).strip()
    if not value.startswith("sha256:"):
        raise _invalid("SCHEMA_FAIL")
    return value


def _build_eval_stage_list(active_ek: dict[str, Any]) -> list[dict[str, Any]]:
    stages = active_ek.get("stages")
    if not isinstance(stages, list):
        raise _invalid("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in stages:
        if not isinstance(row, dict):
            raise _invalid("SCHEMA_FAIL")
        item: dict[str, Any] = {"stage_name": str(row.get("stage_name", "")).strip()}
        if "required_b" in row:
            item["required_b"] = bool(row.get("required_b"))
        if "hard_gate_b" in row:
            item["hard_gate_b"] = bool(row.get("hard_gate_b"))
        if "timeout_ms_max_u64" in row:
            item["timeout_ms_max_u64"] = int(row.get("timeout_ms_max_u64"))
        out.append(item)
    return out


def _base_tree_id_best_effort(repo_root: Path) -> str:
    try:
        return compute_repo_base_tree_id(repo_root)
    except Exception:  # noqa: BLE001
        pass

    run = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
        capture_output=True,
        text=False,
        check=False,
    )
    if run.returncode != 0:
        raise _invalid("MISSING_STATE_INPUT")

    files: list[dict[str, str]] = []
    for raw_rel in sorted(row for row in run.stdout.split(b"\x00") if row):
        rel = raw_rel.decode("utf-8")
        path = (repo_root / rel).resolve()
        if not path.exists() or not path.is_file():
            continue
        files.append(
            {
                "path": rel,
                "sha256": _sha256_prefixed(path.read_bytes()),
            }
        )
    return canon_hash_obj({"schema_version": "ge_ccap_base_tree_fallback_v1", "files": files})


def _build_unified_patch(*, target_relpath: str, before: str, after: str) -> bytes:
    patch_bytes = build_unified_patch_bytes(relpath=target_relpath, before_text=before, after_text=after)
    if not patch_bytes:
        raise _invalid("SITE_NOT_FOUND")
    return patch_bytes


def _build_comment_patch(*, target_relpath: str, marker: str, repo_root: Path) -> bytes:
    target_path = (repo_root / target_relpath).resolve()
    if not target_path.exists() or not target_path.is_file():
        raise _invalid("SITE_NOT_FOUND")
    before = target_path.read_text(encoding="utf-8")
    line = f"# ge_symbiotic_optimizer_v0_3:{marker}"
    if before.endswith("\n"):
        after = before + line + "\n"
    else:
        after = before + "\n" + line + "\n"
    return _build_unified_patch(target_relpath=target_relpath, before=before, after=after)


def _json_path_key(path: tuple[Any, ...]) -> str:
    parts: list[str] = []
    for row in path:
        if isinstance(row, int):
            parts.append(f"[{row}]")
        else:
            parts.append(str(row))
    return "/".join(parts)


def _json_walk_cooldown_paths(node: Any, path: tuple[Any, ...], out: list[tuple[Any, ...]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            next_path = (*path, key)
            if isinstance(value, int) and "cooldown" in str(key).lower():
                out.append(next_path)
            _json_walk_cooldown_paths(value, next_path, out)
        return
    if isinstance(node, list):
        for index, value in enumerate(node):
            _json_walk_cooldown_paths(value, (*path, index), out)


def _json_walk_budget_hint_paths(node: Any, path: tuple[Any, ...], out: list[tuple[Any, ...]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            next_path = (*path, key)
            if (
                str(key) == "budget_cost_hint_q32"
                and isinstance(value, dict)
                and isinstance(value.get("q"), int)
            ):
                out.append((*next_path, "q"))
            _json_walk_budget_hint_paths(value, next_path, out)
        return
    if isinstance(node, list):
        for index, value in enumerate(node):
            _json_walk_budget_hint_paths(value, (*path, index), out)


def _json_get(root: Any, path: tuple[Any, ...]) -> Any:
    node = root
    for key in path:
        node = node[key]
    return node


def _json_set(root: Any, path: tuple[Any, ...], value: Any) -> None:
    node = root
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


def _capability_row_paths(root: Any) -> list[tuple[str, int]]:
    if not isinstance(root, dict):
        return []
    caps = root.get("capabilities")
    if not isinstance(caps, list):
        return []
    rows: list[tuple[str, int]] = []
    for index, row in enumerate(caps):
        if not isinstance(row, dict):
            continue
        campaign_id = str(row.get("campaign_id", "")).strip()
        rows.append((campaign_id, int(index)))
    rows.sort(key=lambda row: (row[0], row[1]))
    return rows


def _deterministic_delta(*, marker: str, template_id: str, target_relpath: str) -> int:
    seed = f"{marker}|{template_id}|{target_relpath}".encode("utf-8")
    return 1 if (int(hashlib.sha256(seed).hexdigest(), 16) % 2 == 0) else -1


def _build_json_tweak_patch(*, target_relpath: str, marker: str, template_id: str, repo_root: Path) -> bytes:
    if template_id not in {
        "JSON_TWEAK_COOLDOWN",
        "JSON_TWEAK_BUDGET_HINT",
        "JSON_TWEAK_COOLDOWN_MINUS_1",
        "JSON_TWEAK_BUDGET_HINT_MINUS_1STEP",
    }:
        raise _invalid("SCHEMA_FAIL")
    target_path = (repo_root / target_relpath).resolve()
    if not target_path.exists() or not target_path.is_file():
        raise _invalid("SITE_NOT_FOUND")

    before_text = target_path.read_text(encoding="utf-8")
    try:
        payload = json.loads(before_text)
    except Exception as exc:  # noqa: BLE001
        raise _invalid("SITE_NOT_FOUND") from exc
    root = copy.deepcopy(payload)

    if template_id == "JSON_TWEAK_COOLDOWN_MINUS_1":
        selected: tuple[Any, ...] | None = None
        for _campaign_id, idx in _capability_row_paths(root):
            row = root["capabilities"][idx]
            value = row.get("cooldown_ticks_u64")
            if isinstance(value, int):
                selected = ("capabilities", idx, "cooldown_ticks_u64")
                break
        if selected is None:
            raise _invalid("SITE_NOT_FOUND")
        current = int(_json_get(root, selected))
        candidate = max(1, current - 1)
        if candidate == current:
            raise _invalid("SITE_NOT_FOUND")
        _json_set(root, selected, int(candidate))
    elif template_id == "JSON_TWEAK_BUDGET_HINT_MINUS_1STEP":
        selected = None
        for _campaign_id, idx in _capability_row_paths(root):
            row = root["capabilities"][idx]
            budget_obj = row.get("budget_cost_hint_q32")
            if isinstance(budget_obj, dict) and isinstance(budget_obj.get("q"), int):
                selected = ("capabilities", idx, "budget_cost_hint_q32", "q")
                break
        if selected is None:
            raise _invalid("SITE_NOT_FOUND")
        current = int(_json_get(root, selected))
        candidate = max(_BUDGET_HINT_MIN_Q32, current - _BUDGET_HINT_STEP_Q32)
        if candidate == current:
            raise _invalid("SITE_NOT_FOUND")
        _json_set(root, selected, int(candidate))
    elif template_id == "JSON_TWEAK_COOLDOWN":
        candidate_paths: list[tuple[Any, ...]] = []
        _json_walk_cooldown_paths(root, tuple(), candidate_paths)
        if not candidate_paths:
            raise _invalid("SITE_NOT_FOUND")
        candidate_paths = sorted(candidate_paths, key=_json_path_key)
        selected = candidate_paths[0]
        current = int(_json_get(root, selected))
        step = _deterministic_delta(marker=marker, template_id=template_id, target_relpath=target_relpath)
        candidate = max(1, min(50, current + step))
        if candidate == current:
            candidate = max(1, min(50, current - step))
        if candidate == current:
            raise _invalid("SITE_NOT_FOUND")
        _json_set(root, selected, int(candidate))
    else:
        candidate_paths = []
        _json_walk_budget_hint_paths(root, tuple(), candidate_paths)
        if not candidate_paths:
            raise _invalid("SITE_NOT_FOUND")
        candidate_paths = sorted(candidate_paths, key=_json_path_key)
        selected = candidate_paths[0]
        current = int(_json_get(root, selected))
        direction = _deterministic_delta(marker=marker, template_id=template_id, target_relpath=target_relpath)
        candidate = current + (direction * _BUDGET_HINT_STEP_Q32)
        candidate = max(_BUDGET_HINT_MIN_Q32, min(_BUDGET_HINT_MAX_Q32, candidate))
        if candidate == current:
            candidate = current - (direction * _BUDGET_HINT_STEP_Q32)
            candidate = max(_BUDGET_HINT_MIN_Q32, min(_BUDGET_HINT_MAX_Q32, candidate))
        if candidate == current:
            raise _invalid("SITE_NOT_FOUND")
        _json_set(root, selected, int(candidate))

    after_text = json.dumps(root, sort_keys=True, separators=(",", ":")) + "\n"
    if not before_text.endswith("\n"):
        before_text = before_text + "\n"
    return _build_unified_patch(target_relpath=target_relpath, before=before_text, after=after_text)


def _build_code_fastpath_guard_patch(*, target_relpath: str, repo_root: Path) -> bytes:
    if target_relpath != _CODE_FASTPATH_TARGET_RELPATH:
        raise _invalid("SITE_NOT_FOUND")
    target_path = (repo_root / target_relpath).resolve()
    if not target_path.exists() or not target_path.is_file():
        raise _invalid("SITE_NOT_FOUND")
    before = target_path.read_text(encoding="utf-8")
    after = before.replace(
        "    output_dir.mkdir(parents=True, exist_ok=True)\n    stdout_path.write_text(proc.stdout, encoding=\"utf-8\")\n",
        "    stdout_path.write_text(proc.stdout, encoding=\"utf-8\")\n",
    )
    after = after.replace(
        "    output_dir.mkdir(parents=True, exist_ok=True)\n    stderr_path.write_text(proc.stderr, encoding=\"utf-8\")\n",
        "    stderr_path.write_text(proc.stderr, encoding=\"utf-8\")\n",
    )
    if after == before:
        raise _invalid("SITE_NOT_FOUND")
    return _build_unified_patch(target_relpath=target_relpath, before=before, after=after)


def _collect_prompt_trace(ge_config: dict[str, Any]) -> tuple[list[dict[str, str]], list[str], bool]:
    traces = ge_config.get("llm_trace")
    if traces is None:
        return [], [], False
    if not isinstance(traces, list):
        raise _invalid("SCHEMA_FAIL")
    rows: list[dict[str, str]] = []
    prompt_hashes: list[str] = []
    for row in traces:
        if not isinstance(row, dict):
            raise _invalid("SCHEMA_FAIL")
        prompt = str(row.get("prompt", ""))
        response = str(row.get("response", ""))
        prompt_hash = _sha256_prefixed(prompt.encode("utf-8"))
        response_hash = _sha256_prefixed(response.encode("utf-8"))
        prompt_hashes.append(prompt_hash)
        rows.append({"prompt_hash": prompt_hash, "response_hash": response_hash})
    return rows, prompt_hashes, True


def _iso_utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_openai_model(model_id: str) -> str:
    value = str(model_id).strip()
    if not value.startswith(("gpt-", "o1", "o3", "o4")):
        raise _invalid("SCHEMA_FAIL")
    return value


def _validate_anthropic_model(model_id: str) -> str:
    value = str(model_id).strip()
    if not value.startswith("claude-"):
        raise _invalid("SCHEMA_FAIL")
    return value


def _http_post_json(*, url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    req = Request(url=url, data=json.dumps(payload, separators=(",", ":")).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(str(key), str(value))
    try:
        with urlopen(req, timeout=60) as resp:  # nosec: B310
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM_HTTP_ERROR:{exc.code}:{detail[:240]}") from exc
    except URLError as exc:
        raise RuntimeError(f"LLM_HTTP_ERROR:{exc}") from exc
    payload_obj = json.loads(raw)
    if not isinstance(payload_obj, dict):
        raise _invalid("SCHEMA_FAIL")
    return payload_obj


def _extract_openai_response_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text
    outputs = payload.get("output")
    chunks: list[str] = []
    if isinstance(outputs, list):
        for row in outputs:
            if not isinstance(row, dict):
                continue
            content = row.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if str(block.get("type", "")).strip() not in {"output_text", "text"}:
                    continue
                text = block.get("text")
                if isinstance(text, str) and text:
                    chunks.append(text)
    response = "".join(chunks).strip()
    if not response:
        raise RuntimeError("LLM_RESPONSE_EMPTY")
    return response


def _extract_anthropic_response_text(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        raise RuntimeError("LLM_RESPONSE_EMPTY")
    chunks: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if str(block.get("type", "")).strip() != "text":
            continue
        text = block.get("text")
        if isinstance(text, str) and text:
            chunks.append(text)
    response = "".join(chunks).strip()
    if not response:
        raise RuntimeError("LLM_RESPONSE_EMPTY")
    return response


def _append_replay_row(replay_path: Path, row: dict[str, Any]) -> None:
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    with replay_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _lookup_replay_response(*, replay_path: Path, provider: str, model: str, prompt: str) -> str:
    if not replay_path.exists():
        raise _LLMReplayMissError("LLM_REPLAY_MISS")
    prompt_hash = _sha256_prefixed(prompt.encode("utf-8"))
    for line in replay_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise _invalid("SCHEMA_FAIL")
        if str(payload.get("schema_version", "")).strip() != _LLM_REPLAY_SCHEMA_VERSION:
            continue
        if str(payload.get("backend", "")).strip() != provider:
            continue
        if str(payload.get("model", "")).strip() != model:
            continue
        if str(payload.get("prompt_sha256", "")).strip() != prompt_hash:
            continue
        response = payload.get("response")
        if not isinstance(response, str):
            raise _invalid("SCHEMA_FAIL")
        if str(payload.get("response_sha256", "")).strip() != _sha256_prefixed(response.encode("utf-8")):
            raise _invalid("SCHEMA_FAIL")
        return response
    raise _LLMReplayMissError("LLM_REPLAY_MISS")


def _selector_backend_response(*, backend: str, model: str, prompt: str) -> tuple[str, str]:
    replay_path_raw = str(os.environ.get("ORCH_LLM_REPLAY_PATH", "")).strip()
    if not replay_path_raw:
        raise RuntimeError("LLM_REPLAY_PATH_MISSING")
    replay_path = Path(replay_path_raw).expanduser().resolve()

    backend_key = str(backend).strip()
    if backend_key in {"openai_replay", "openai_harvest"}:
        provider = "openai"
        model_id = _validate_openai_model(model)
    elif backend_key in {"anthropic_replay", "anthropic_harvest"}:
        provider = "anthropic"
        model_id = _validate_anthropic_model(model)
    else:
        raise _invalid("SCHEMA_FAIL")

    if backend_key.endswith("_replay"):
        return _lookup_replay_response(replay_path=replay_path, provider=provider, model=model_id, prompt=prompt), model_id

    if str(os.environ.get("ORCH_LLM_LIVE_OK", "")).strip() != "1":
        raise RuntimeError("LLM_LIVE_DISABLED")

    if provider == "openai":
        api_key = str(os.environ.get("OPENAI_API_KEY", "")).strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY_MISSING")
        raw_payload = _http_post_json(
            url="https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}"},
            payload={"model": model_id, "input": prompt},
        )
        response = _extract_openai_response_text(raw_payload)
    else:
        api_key = str(os.environ.get("ANTHROPIC_API_KEY", "")).strip()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY_MISSING")
        version = str(os.environ.get("ORCH_ANTHROPIC_VERSION", "2023-06-01")).strip() or "2023-06-01"
        raw_payload = _http_post_json(
            url="https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": version},
            payload={
                "model": model_id,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response = _extract_anthropic_response_text(raw_payload)

    replay_row = {
        "schema_version": _LLM_REPLAY_SCHEMA_VERSION,
        "backend": provider,
        "model": model_id,
        "prompt_sha256": _sha256_prefixed(prompt.encode("utf-8")),
        "response_sha256": _sha256_prefixed(response.encode("utf-8")),
        "prompt": prompt,
        "response": response,
        "created_at_utc": _iso_utc_now(),
        "raw_response_json": raw_payload,
    }
    _append_replay_row(replay_path, replay_row)
    return response, model_id


def _normalize_metric_for_prompt(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value.keys()) == {"q"}:
            return int(value.get("q", 0))
        if set(value.keys()) == {"num_u64", "den_u64"}:
            num = max(0, int(value.get("num_u64", 0)))
            den = max(1, int(value.get("den_u64", 1)))
            return {"num_u64": num, "den_u64": den}
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _normalized_skill_metrics_for_prompt(observation_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(observation_payload, dict):
        return {}
    metrics = observation_payload.get("metrics")
    if not isinstance(metrics, dict):
        return {}
    out: dict[str, Any] = {}
    for key in sorted(metrics.keys()):
        normalized = _normalize_metric_for_prompt(metrics.get(key))
        if normalized is not None:
            out[str(key)] = normalized
    return out


def _selector_prompt(
    *,
    skill_metrics: dict[str, Any],
    allowed_targets: list[str],
    allowed_templates: list[str],
    candidates: list[dict[str, str]],
    max_select: int,
) -> str:
    prompt_payload = {
        "schema_version": "ge_llm_selector_prompt_v1",
        "task": "Select the best patch candidates and return JSON only.",
        "skill_metrics": skill_metrics,
        "allowed_targets": allowed_targets,
        "allowed_templates": allowed_templates,
        "max_select_u64": int(max_select),
        "candidates": candidates,
        "required_output_json": {
            "type": "array",
            "items": {"template_id": "string", "target_relpath": "string"},
        },
    }
    return json.dumps(prompt_payload, sort_keys=True, separators=(",", ":"))


def _parse_selector_response(response_text: str) -> list[dict[str, str]]:
    payload = json.loads(response_text)
    rows: Any = payload
    if isinstance(payload, dict):
        rows = payload.get("selections")
    if not isinstance(rows, list):
        raise RuntimeError("LLM_SELECTOR_INVALID")
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        template_id = str(row.get("template_id", "")).strip()
        target_relpath = _normalize_relpath(str(row.get("target_relpath", "")).strip())
        if template_id and target_relpath:
            out.append({"template_id": template_id, "target_relpath": target_relpath})
    return out


def _select_with_llm_selector(
    *,
    selector_cfg: dict[str, Any],
    candidates: list[dict[str, str]],
    allowed_targets: list[str],
    allowed_templates: list[str],
    max_ccaps: int,
    latest_observation: dict[str, Any] | None,
) -> tuple[list[dict[str, str]], list[dict[str, str]], str | None]:
    enabled_b = bool(selector_cfg.get("enabled_b", False))
    if not enabled_b:
        return list(candidates[:max_ccaps]), [], None

    backend = str(selector_cfg.get("backend", "")).strip()
    model = str(selector_cfg.get("model", "")).strip()
    max_proposals_u64 = max(1, int(selector_cfg.get("max_proposals_u64", 8)))
    candidate_pool = list(candidates[:max_proposals_u64])
    if not candidate_pool:
        return [], [], "LLM_SELECTOR_EMPTY_POOL"

    prompt = _selector_prompt(
        skill_metrics=_normalized_skill_metrics_for_prompt(latest_observation),
        allowed_targets=allowed_targets,
        allowed_templates=allowed_templates,
        candidates=[{"template_id": row["template_id"], "target_relpath": row["target_relpath"]} for row in candidate_pool],
        max_select=max_ccaps,
    )
    prompt_hash = _sha256_prefixed(prompt.encode("utf-8"))

    try:
        response, resolved_model = _selector_backend_response(backend=backend, model=model, prompt=prompt)
    except _LLMReplayMissError:
        return [], [], "LLM_REPLAY_MISS"
    except Exception as exc:  # noqa: BLE001
        return [], [], f"LLM_SELECTOR_ERROR:{exc}"

    response_hash = _sha256_prefixed(response.encode("utf-8"))
    prompt_rows = [{"prompt_hash": prompt_hash, "response_hash": response_hash}]

    try:
        parsed = _parse_selector_response(response)
    except Exception:  # noqa: BLE001
        return [], prompt_rows, "LLM_SELECTOR_INVALID"

    candidate_map = {
        (str(row["template_id"]), str(row["target_relpath"])): row
        for row in candidate_pool
    }
    selected: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in parsed:
        key = (row["template_id"], row["target_relpath"])
        if key not in candidate_map or key in seen:
            continue
        seen.add(key)
        candidate_row = candidate_map[key]
        selected.append(
            {
                "bucket": str(candidate_row.get("bucket", "")),
                "template_id": key[0],
                "target_relpath": key[1],
                "model": resolved_model,
            }
        )
        if len(selected) >= max_ccaps:
            break
    if not selected:
        return [], prompt_rows, "LLM_SELECTOR_EMPTY_SELECTION"
    return selected, prompt_rows, None


def _resolved_ge_state_root(raw_arg: str) -> Path:
    value = str(raw_arg).strip()
    if value:
        return Path(value).expanduser().resolve()
    env_value = str(os.environ.get("OMEGA_GE_STATE_ROOT", "")).strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return (REPO_ROOT / ".omega_cache" / "genesis_engine").resolve()


def _latest_observation_payload(*, repo_root: Path, recent_runs_root: Path | None) -> dict[str, Any] | None:
    candidates: list[Path] = []
    if recent_runs_root is not None and recent_runs_root.exists() and recent_runs_root.is_dir():
        candidates.extend(
            sorted(
                recent_runs_root.glob("*/daemon/rsi_omega_daemon_v18_0/state/observations/sha256_*.omega_observation_report_v1.json"),
                key=lambda row: row.as_posix(),
            )
        )
    elif (repo_root / "daemon" / "rsi_omega_daemon_v18_0" / "state" / "observations").exists():
        candidates.extend(
            sorted(
                (repo_root / "daemon" / "rsi_omega_daemon_v18_0" / "state" / "observations").glob(
                    "sha256_*.omega_observation_report_v1.json"
                ),
                key=lambda row: row.as_posix(),
            )
        )
    if not candidates:
        return None

    best_payload: dict[str, Any] | None = None
    best_tick = -1
    best_path = ""
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        if str(payload.get("schema_version", "")).strip() != "omega_observation_report_v1":
            continue
        tick_u64 = int(payload.get("tick_u64", -1))
        if tick_u64 < 0:
            continue
        path_key = path.as_posix()
        if tick_u64 > best_tick or (tick_u64 == best_tick and path_key > best_path):
            best_tick = tick_u64
            best_path = path_key
            best_payload = payload
    return best_payload


def _metric_q32(metrics: Any, key: str) -> int:
    if not isinstance(metrics, dict):
        return 0
    row = metrics.get(key)
    if not isinstance(row, dict):
        return 0
    return int(row.get("q", 0))


def _metric_q32_series(metric_series: Any, key: str) -> list[int]:
    if not isinstance(metric_series, dict):
        return []
    rows = metric_series.get(key)
    if not isinstance(rows, list):
        return []
    out: list[int] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(int(row.get("q", 0)))
    return out


def _source_schema_ids(observation_payload: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    rows = observation_payload.get("sources")
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.add(str(row.get("schema_id", "")).strip())
    return out


def _derive_skill_policy_from_observation_payload(observation_payload: dict[str, Any] | None) -> dict[str, Any]:
    default_policy = {
        "schema_version": "ge_skill_policy_v1",
        "source_observation_hash": _sha256_prefixed(b""),
        "mode": "DEFAULT",
        "has_thermo_skill_b": False,
        "has_flywheel_skill_b": False,
        "has_persistence_skill_b": False,
        "has_model_genesis_skill_b": False,
        "thermo_efficiency_q32": 0,
        "flywheel_yield_q32": 0,
        "persistence_health_q32": 0,
        "dataset_refresh_needed_b_q32": 0,
        "thermo_worsened_b": False,
        "flywheel_plateau_b": False,
        "persistence_unhealthy_b": False,
        "dataset_refresh_needed_b": False,
    }
    if observation_payload is None:
        return default_policy

    source_ids = _source_schema_ids(observation_payload)
    metrics = observation_payload.get("metrics")
    metric_series = observation_payload.get("metric_series")

    has_thermo_skill_b = "omega_skill_thermo_report_v1" in source_ids
    has_flywheel_skill_b = "omega_skill_eff_flywheel_report_v1" in source_ids
    has_persistence_skill_b = "omega_skill_persistence_report_v1" in source_ids
    has_model_genesis_skill_b = "omega_skill_model_genesis_report_v1" in source_ids

    thermo_efficiency_q32 = _metric_q32(metrics, "thermo_efficiency_q32")
    flywheel_yield_q32 = _metric_q32(metrics, "flywheel_yield_q32")
    persistence_health_q32 = _metric_q32(metrics, "persistence_health_q32")
    dataset_refresh_needed_b_q32 = _metric_q32(metrics, "dataset_refresh_needed_b_q32")

    thermo_series = _metric_q32_series(metric_series, "thermo_efficiency_q32")
    flywheel_series = _metric_q32_series(metric_series, "flywheel_yield_q32")

    thermo_worsened_b = bool(
        has_thermo_skill_b
        and len(thermo_series) >= 2
        and int(thermo_series[-1]) < int(thermo_series[-2])
    )

    flywheel_plateau_b = False
    if has_flywheel_skill_b and len(flywheel_series) >= 3:
        flywheel_plateau_b = bool(
            int(flywheel_series[-1]) <= int(flywheel_series[-2]) <= int(flywheel_series[-3])
        )
    elif has_flywheel_skill_b and len(flywheel_series) == 2:
        flywheel_plateau_b = bool(int(flywheel_series[-1]) <= int(flywheel_series[-2]))

    persistence_unhealthy_b = bool(has_persistence_skill_b and persistence_health_q32 < _Q32_ONE)
    dataset_refresh_needed_b = bool(has_model_genesis_skill_b and dataset_refresh_needed_b_q32 >= _Q32_ONE)

    mode = "DEFAULT"
    if persistence_unhealthy_b:
        mode = "DIAGNOSTIC_ONLY"
    elif thermo_worsened_b or flywheel_plateau_b or dataset_refresh_needed_b:
        mode = "STEERED"

    return {
        "schema_version": "ge_skill_policy_v1",
        "source_observation_hash": canon_hash_obj(observation_payload),
        "mode": mode,
        "has_thermo_skill_b": bool(has_thermo_skill_b),
        "has_flywheel_skill_b": bool(has_flywheel_skill_b),
        "has_persistence_skill_b": bool(has_persistence_skill_b),
        "has_model_genesis_skill_b": bool(has_model_genesis_skill_b),
        "thermo_efficiency_q32": int(thermo_efficiency_q32),
        "flywheel_yield_q32": int(flywheel_yield_q32),
        "persistence_health_q32": int(persistence_health_q32),
        "dataset_refresh_needed_b_q32": int(dataset_refresh_needed_b_q32),
        "thermo_worsened_b": bool(thermo_worsened_b),
        "flywheel_plateau_b": bool(flywheel_plateau_b),
        "persistence_unhealthy_b": bool(persistence_unhealthy_b),
        "dataset_refresh_needed_b": bool(dataset_refresh_needed_b),
    }


def _apply_skill_policy_to_bucket_plan(*, bucket_plan: dict[str, int], skill_policy: dict[str, Any]) -> dict[str, int]:
    out = {
        "opt": int(bucket_plan.get("opt", 0)),
        "nov": int(bucket_plan.get("nov", 0)),
        "grow": int(bucket_plan.get("grow", 0)),
    }
    if bool(skill_policy.get("flywheel_plateau_b", False)):
        if out["opt"] > 0:
            out["opt"] -= 1
            out["nov"] += 1
        elif out["grow"] > 0:
            out["grow"] -= 1
            out["nov"] += 1
    if bool(skill_policy.get("dataset_refresh_needed_b", False)):
        if out["opt"] > 0:
            out["opt"] -= 1
            out["grow"] += 1
        elif out["nov"] > 0:
            out["nov"] -= 1
            out["grow"] += 1
    return out


def _prioritize_targets_for_speedup(*, targets: list[str], speedup_mode_b: bool) -> list[str]:
    if not speedup_mode_b:
        return list(targets)
    stable_order = {target: idx for idx, target in enumerate(targets)}
    return sorted(
        targets,
        key=lambda target: (
            0 if target in _SPEEDUP_TARGET_RELPATHS else 1,
            stable_order.get(target, 0),
            target,
        ),
    )


def _prioritize_targets_for_model_genesis(*, targets: list[str], dataset_refresh_needed_b: bool) -> list[str]:
    if not dataset_refresh_needed_b:
        return list(targets)
    stable_order = {target: idx for idx, target in enumerate(targets)}
    return sorted(
        targets,
        key=lambda target: (
            0
            if (
                _MODEL_GENESIS_TARGET_HINT in str(target)
                or str(target).endswith("omega_capability_registry_v2.json")
            )
            else 1,
            stable_order.get(target, 0),
            target,
        ),
    )


def _bucket_plan(*, ge_config: dict[str, Any], max_ccaps: int) -> dict[str, int]:
    n = max(1, min(8, int(max_ccaps)))
    if n < 3:
        out = {"opt": 0, "nov": 0, "grow": 0}
        if n >= 1:
            out["opt"] = 1
        if n >= 2:
            out["nov"] = 1
        return out

    fracs = ge_config.get("bucket_fracs_q32")
    mins = ge_config.get("bucket_min_counts")
    if not isinstance(fracs, dict) or not isinstance(mins, dict):
        raise _invalid("SCHEMA_FAIL")

    counts = {
        "opt": int((n * int(fracs.get("opt_q32", 0))) // _Q32_ONE),
        "nov": int((n * int(fracs.get("nov_q32", 0))) // _Q32_ONE),
        "grow": int((n * int(fracs.get("grow_q32", 0))) // _Q32_ONE),
    }
    remainder = n - (counts["opt"] + counts["nov"] + counts["grow"])
    for bucket in ("opt", "nov", "grow"):
        if remainder <= 0:
            break
        counts[bucket] += 1
        remainder -= 1

    min_counts = {
        "opt": max(0, int(mins.get("opt_u64", 0))),
        "nov": max(0, int(mins.get("nov_u64", 0))),
        "grow": max(0, int(mins.get("grow_u64", 0))),
    }

    for bucket in ("opt", "nov", "grow"):
        deficit = max(0, min_counts[bucket] - counts[bucket])
        if deficit == 0:
            continue
        for donor in ("opt", "nov"):
            if donor == bucket:
                continue
            available = max(0, counts[donor] - min_counts[donor])
            if available <= 0:
                continue
            transfer = min(deficit, available)
            counts[donor] -= transfer
            counts[bucket] += transfer
            deficit -= transfer
            if deficit == 0:
                break

    return {"opt": int(counts["opt"]), "nov": int(counts["nov"]), "grow": int(counts["grow"])}


def _empty_target_stats() -> dict[str, int]:
    return {
        "seen_u64": 0,
        "promote_u64": 0,
        "busy_fail_u64": 0,
        "cost_wall_ms_u64": 0,
        "mean_yield_q32": 0,
        "busy_fail_rate_q32": 0,
    }


def _target_stats_from_events(*, events: list[dict[str, Any]], allowed_targets: list[str]) -> dict[str, dict[str, int]]:
    out = {target: _empty_target_stats() for target in allowed_targets}
    for event in events:
        pd_features = event.get("pd_features")
        receipt = event.get("receipt_payload")
        behavior_sig = event.get("behavior_sig")
        if not isinstance(pd_features, dict) or not isinstance(receipt, dict) or not isinstance(behavior_sig, dict):
            raise _invalid("SCHEMA_FAIL")
        touched_paths = pd_features.get("touched_paths")
        if not isinstance(touched_paths, list):
            raise _invalid("SCHEMA_FAIL")
        phi = behavior_sig.get("phi")
        if not isinstance(phi, list) or len(phi) < 4:
            raise _invalid("SCHEMA_FAIL")
        sentinel = int(phi[3])
        cost_vector = receipt.get("cost_vector")
        if not isinstance(cost_vector, dict):
            raise _invalid("SCHEMA_FAIL")

        for raw_path in sorted({str(row) for row in touched_paths}):
            target = _normalize_relpath(raw_path)
            if target not in out:
                continue
            row = out[target]
            row["seen_u64"] = int(row["seen_u64"]) + 1
            if str(receipt.get("decision", "")).strip() == "PROMOTE":
                row["promote_u64"] = int(row["promote_u64"]) + 1
            if sentinel == 1:
                row["busy_fail_u64"] = int(row["busy_fail_u64"]) + 1
            row["cost_wall_ms_u64"] = int(row["cost_wall_ms_u64"]) + max(0, int(cost_vector.get("wall_ms", 0)))

    for target, row in out.items():
        seen = max(0, int(row["seen_u64"]))
        promote = max(0, int(row["promote_u64"]))
        busy_fail = max(0, int(row["busy_fail_u64"]))
        row["mean_yield_q32"] = int(rat_q32(promote, max(1, seen)))
        row["busy_fail_rate_q32"] = int(rat_q32(busy_fail, max(1, seen)))
        out[target] = row
    return out


def _ranked_targets_for_bucket(
    *,
    bucket: str,
    allowed_targets: list[str],
    target_stats: dict[str, dict[str, int]],
) -> list[str]:
    def _stats(target: str) -> dict[str, int]:
        return target_stats.get(target, _empty_target_stats())

    if bucket == "opt":
        return sorted(
            allowed_targets,
            key=lambda target: (
                -int(_stats(target)["mean_yield_q32"]),
                int(_stats(target)["seen_u64"]),
                target,
            ),
        )
    if bucket == "nov":
        return sorted(
            allowed_targets,
            key=lambda target: (
                int(_stats(target)["seen_u64"]),
                target,
            ),
        )
    if bucket == "grow":
        return sorted(
            allowed_targets,
            key=lambda target: (
                -int(_stats(target)["busy_fail_rate_q32"]),
                -int(_stats(target)["cost_wall_ms_u64"]),
                target,
            ),
        )
    raise _invalid("SCHEMA_FAIL")


def _template_for_bucket(*, ge_config: dict[str, Any], bucket: str) -> str | None:
    proposal = ge_config.get("proposal_space_patch")
    if not isinstance(proposal, dict):
        raise _invalid("SCHEMA_FAIL")
    templates = proposal.get("templates")
    if not isinstance(templates, list):
        raise _invalid("SCHEMA_FAIL")
    for row in templates:
        if not isinstance(row, dict):
            continue
        if str(row.get("bucket", "")).strip() != bucket:
            continue
        template_id = str(row.get("template_id", "")).strip()
        if template_id in _SUPPORTED_TEMPLATE_IDS:
            return template_id
    return None


def _template_supports_target(*, template_id: str, target_relpath: str) -> bool:
    if template_id in {
        "JSON_TWEAK_COOLDOWN",
        "JSON_TWEAK_BUDGET_HINT",
        "JSON_TWEAK_COOLDOWN_MINUS_1",
        "JSON_TWEAK_BUDGET_HINT_MINUS_1STEP",
    }:
        return str(target_relpath).endswith(".json")
    if template_id == "CODE_FASTPATH_GUARD":
        return str(target_relpath).strip() == _CODE_FASTPATH_TARGET_RELPATH
    return True


def _hard_avoid_prefixes(snapshot: dict[str, Any]) -> set[str]:
    rows = snapshot.get("hard_avoid_set")
    if not isinstance(rows, list):
        raise _invalid("SCHEMA_FAIL")
    out: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise _invalid("SCHEMA_FAIL")
        prefix = str(row.get("touched_paths_hash_prefix_hex", "")).strip()
        out.add(prefix)
    return out


def _eligible_target(
    *,
    target_relpath: str,
    repo_root: Path,
    ge_config: dict[str, Any],
    hard_avoid_prefixes: set[str],
) -> bool:
    relpath = _normalize_relpath(target_relpath)
    if not (repo_root / relpath).exists():
        return False

    hard_avoid_cfg = ge_config.get("hard_avoid")
    if not isinstance(hard_avoid_cfg, dict):
        raise _invalid("SCHEMA_FAIL")
    if not bool(hard_avoid_cfg.get("enabled_b", False)):
        return True

    projection = hard_avoid_cfg.get("pd_projection")
    if not isinstance(projection, dict):
        raise _invalid("SCHEMA_FAIL")
    prefix_len = int(projection.get("touched_paths_prefix_hex_u8", 0))

    touched_paths_hash = touched_paths_hash_for_paths([relpath])
    prefix = touched_paths_hash_prefix_hex(
        touched_paths_hash=touched_paths_hash,
        prefix_hex_u8=prefix_len,
    )
    return prefix not in hard_avoid_prefixes


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(path, payload)


def _emit_ccap(
    *,
    repo_root: Path,
    out_dir: Path,
    pins: dict[str, Any],
    active_ek: dict[str, Any],
    auth_hash_value: str,
    build_recipe_id: str,
    base_tree_id: str,
    target_relpath: str,
    marker: str,
    size_buckets_bytes_u64: list[int],
    bucket: str,
    template_id: str,
) -> dict[str, Any]:
    if template_id == "COMMENT_APPEND":
        patch_bytes = _build_comment_patch(target_relpath=target_relpath, marker=marker, repo_root=repo_root)
    elif template_id in {
        "JSON_TWEAK_COOLDOWN",
        "JSON_TWEAK_BUDGET_HINT",
        "JSON_TWEAK_COOLDOWN_MINUS_1",
        "JSON_TWEAK_BUDGET_HINT_MINUS_1STEP",
    }:
        patch_bytes = _build_json_tweak_patch(
            target_relpath=target_relpath,
            marker=marker,
            template_id=template_id,
            repo_root=repo_root,
        )
    elif template_id == "CODE_FASTPATH_GUARD":
        patch_bytes = _build_code_fastpath_guard_patch(
            target_relpath=target_relpath,
            repo_root=repo_root,
        )
    else:
        raise _invalid("SCHEMA_FAIL")
    patch_blob_id = _sha256_prefixed(patch_bytes)

    payload = {
        "kind": "PATCH",
        "patch_blob_id": patch_blob_id,
    }
    ccap_id = ccap_payload_id({"payload": payload})
    ccap_hex = ccap_id.split(":", 1)[1]

    op_pool_ids = pins.get("active_op_pool_ids")
    dsbx_ids = pins.get("active_dsbx_profile_ids")
    if not isinstance(op_pool_ids, list) or not op_pool_ids:
        raise _invalid("MISSING_STATE_INPUT")
    if not isinstance(dsbx_ids, list) or not dsbx_ids:
        raise _invalid("MISSING_STATE_INPUT")

    # Survival Drill v1: the default wallclock budget (10 minutes) is too tight for
    # deterministic repo-harness runs on some machines. In the drill only, allow
    # a larger wallclock cap so CCAP can be promoted without weakening verifier checks.
    wall_ms_max = 600000
    if str(os.environ.get("OMEGA_SURVIVAL_DRILL", "")).strip().lower() in {"1", "true", "yes", "on"}:
        wall_ms_max = 1200000

    ccap_obj = {
        "meta": {
            "ccap_version": 1,
            "base_tree_id": base_tree_id,
            "auth_hash": auth_hash_value,
            "dsbx_profile_id": str(dsbx_ids[0]),
            "env_contract_id": str(pins["env_contract_id"]),
            "toolchain_root_id": str(pins["toolchain_root_id"]),
            "ek_id": str(pins["active_ek_id"]),
            "op_pool_id": str(op_pool_ids[0]),
            "canon_version_ids": dict(pins["canon_version_ids"]),
        },
        "payload": payload,
        "build": {
            "build_recipe_id": build_recipe_id,
            "build_targets": [],
            "artifact_bindings": {},
        },
        "eval": {
            "stages": _build_eval_stage_list(active_ek),
            "final_suite_id": canon_hash_obj(
                {
                    "schema_version": "ge_final_suite_v0_3",
                    "build_recipe_id": build_recipe_id,
                    "ek_id": pins["active_ek_id"],
                }
            ),
        },
        "budgets": {
            "cpu_ms_max": 600000,
            "wall_ms_max": wall_ms_max,
            "mem_mb_max": 4096,
            "disk_mb_max": 2048,
            "fds_max": 256,
            "procs_max": 64,
            "threads_max": 256,
            "net": "forbidden",
        },
    }
    validate_schema(ccap_obj, "ccap_v1")

    ccap_dir = out_dir / "ccap"
    blobs_dir = ccap_dir / "blobs"
    blobs_dir.mkdir(parents=True, exist_ok=True)

    patch_path = blobs_dir / f"sha256_{patch_blob_id.split(':', 1)[1]}.patch"
    patch_path.write_bytes(patch_bytes)

    ccap_path = ccap_dir / f"sha256_{ccap_hex}.ccap_v1.json"
    _write_json(ccap_path, ccap_obj)

    pd_payload, _pd_features = build_pd_from_patch_bytes(
        patch_bytes=patch_bytes,
        base_tree_id=base_tree_id,
        ek_id=str(pins["active_ek_id"]),
        op_pool_id=str(op_pool_ids[0]),
        size_buckets_bytes_u64=size_buckets_bytes_u64,
    )
    validate_schema(pd_payload, "ge_pd_v1")

    return {
        "bucket": bucket,
        "template_id": template_id,
        "ccap_id": ccap_id,
        "ccap_relpath": ccap_path.relative_to(out_dir).as_posix(),
        "patch_blob_id": patch_blob_id,
        "patch_relpath": patch_path.relative_to(out_dir).as_posix(),
        "target_relpath": target_relpath,
        "pd_id": str(pd_payload["pd_id"]),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ge_symbiotic_optimizer_v0_3")
    parser.add_argument("--subrun_out_dir", required=True)
    parser.add_argument("--ge_config_path", required=True)
    parser.add_argument("--authority_pins_path", required=True)
    parser.add_argument("--recent_runs_root", default="")
    parser.add_argument("--ge_state_root", default="")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--model_id", default="ge-v0_3")
    parser.add_argument("--max_ccaps", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    repo_root = REPO_ROOT.resolve()

    subrun_out_dir = Path(args.subrun_out_dir).expanduser().resolve()
    ge_config_path = Path(args.ge_config_path).expanduser().resolve()
    authority_pins_path = Path(args.authority_pins_path).expanduser().resolve()
    recent_runs_root = Path(args.recent_runs_root).expanduser().resolve() if str(args.recent_runs_root).strip() else None
    ge_state_root = _resolved_ge_state_root(str(args.ge_state_root))
    seed = max(0, int(args.seed))
    model_id = str(args.model_id).strip() or "ge-v0_3"
    max_ccaps = max(1, min(8, int(args.max_ccaps)))

    ge_config = load_ge_config(ge_config_path)
    validate_schema(ge_config, "ge_config_v1")

    # The CLI allows explicit pin paths but governance authority remains a single, explicit payload.
    # In survival drill runs we allow a drill-only pins file (selected via OMEGA_AUTHORITY_PINS_REL)
    # while keeping the check fail-closed: the caller must pass the exact resolved path.
    pins_rel = str(os.environ.get("OMEGA_AUTHORITY_PINS_REL", "authority/authority_pins_v1.json")).strip()
    if not pins_rel:
        pins_rel = "authority/authority_pins_v1.json"
    expected_authority_path = (repo_root / pins_rel).resolve()
    if authority_pins_path != expected_authority_path:
        raise _invalid("SCHEMA_FAIL")
    pins = load_authority_pins(repo_root)
    authority_pins_hash = _sha256_prefixed(canon_bytes(pins))
    auth_hash_value = auth_hash(pins)

    xs_snapshot, xs_events = build_xs_snapshot(
        recent_runs_root=recent_runs_root,
        ge_config=ge_config,
        authority_pins_hash=authority_pins_hash,
    )

    subrun_out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(subrun_out_dir / "ge_xs_snapshot_v1.json", xs_snapshot)

    ge_state_root.mkdir(parents=True, exist_ok=True)
    xs_hex = str(xs_snapshot["xs_id"]).split(":", 1)[1]
    _write_json(ge_state_root / "ge_xs_snapshot_v1.json", xs_snapshot)
    _write_json(ge_state_root / "snapshots" / f"sha256_{xs_hex}.ge_xs_snapshot_v1.json", xs_snapshot)

    trace_prompt_rows, _trace_prompt_hashes, _has_trace = _collect_prompt_trace(ge_config)
    latest_observation = _latest_observation_payload(repo_root=repo_root, recent_runs_root=recent_runs_root)
    skill_policy = _derive_skill_policy_from_observation_payload(latest_observation)
    skill_policy_hash = canon_hash_obj(skill_policy)

    proposal_cfg = ge_config.get("proposal_space_patch")
    if not isinstance(proposal_cfg, dict):
        raise _invalid("SCHEMA_FAIL")
    allowed_targets_raw = proposal_cfg.get("allowed_target_relpaths")
    if not isinstance(allowed_targets_raw, list) or not allowed_targets_raw:
        raise _invalid("SCHEMA_FAIL")
    allowed_targets = [_normalize_relpath(str(row)) for row in allowed_targets_raw]

    size_buckets = proposal_cfg.get("size_buckets_bytes_u64")
    if not isinstance(size_buckets, list) or not size_buckets:
        raise _invalid("SCHEMA_FAIL")
    size_buckets_u64 = [int(row) for row in size_buckets]
    templates_cfg = proposal_cfg.get("templates")
    if not isinstance(templates_cfg, list):
        raise _invalid("SCHEMA_FAIL")
    allowed_templates = sorted(
        {
            str(row.get("template_id", "")).strip()
            for row in templates_cfg
            if isinstance(row, dict) and str(row.get("template_id", "")).strip() in _SUPPORTED_TEMPLATE_IDS
        }
    )

    llm_selector_cfg_raw = ge_config.get("llm_selector")
    if llm_selector_cfg_raw is None:
        llm_selector_cfg: dict[str, Any] = {
            "enabled_b": False,
            "backend": "",
            "model": "",
            "max_proposals_u64": 8,
        }
    elif isinstance(llm_selector_cfg_raw, dict):
        llm_selector_cfg = dict(llm_selector_cfg_raw)
    else:
        raise _invalid("SCHEMA_FAIL")

    target_stats = _target_stats_from_events(events=xs_events, allowed_targets=allowed_targets)
    bucket_plan = _bucket_plan(ge_config=ge_config, max_ccaps=max_ccaps)
    bucket_plan = _apply_skill_policy_to_bucket_plan(bucket_plan=bucket_plan, skill_policy=skill_policy)

    hard_avoid_prefixes = _hard_avoid_prefixes(xs_snapshot)

    active_ek = _load_active_ek(repo_root, str(pins["active_ek_id"]))
    recipes = _load_build_recipes(repo_root)
    build_recipe_id = _resolve_default_recipe_id(recipes)
    base_tree_id = _base_tree_id_best_effort(repo_root)

    planned_candidates: list[dict[str, str]] = []
    for bucket in ("opt", "nov", "grow"):
        target_count = int(bucket_plan.get(bucket, 0))
        if target_count <= 0:
            continue
        template_id = _template_for_bucket(ge_config=ge_config, bucket=bucket)
        if template_id is None:
            continue

        ranked_targets = _ranked_targets_for_bucket(
            bucket=bucket,
            allowed_targets=allowed_targets,
            target_stats=target_stats,
        )
        ranked_targets = _prioritize_targets_for_speedup(
            targets=ranked_targets,
            speedup_mode_b=bool(skill_policy.get("thermo_worsened_b", False)) and bucket == "opt",
        )
        ranked_targets = _prioritize_targets_for_model_genesis(
            targets=ranked_targets,
            dataset_refresh_needed_b=bool(skill_policy.get("dataset_refresh_needed_b", False)),
        )
        eligible_targets = [
            target
            for target in ranked_targets
            if _eligible_target(
                target_relpath=target,
                repo_root=repo_root,
                ge_config=ge_config,
                hard_avoid_prefixes=hard_avoid_prefixes,
            )
            and _template_supports_target(template_id=template_id, target_relpath=target)
        ]
        if template_id in {"JSON_TWEAK_COOLDOWN", "JSON_TWEAK_BUDGET_HINT"}:
            eligible_targets = sorted(
                eligible_targets,
                key=lambda target: (
                    int(target_stats.get(target, _empty_target_stats()).get("seen_u64", 0)),
                    target,
                ),
            )

        for target in eligible_targets[:target_count]:
            planned_candidates.append(
                {
                    "bucket": bucket,
                    "template_id": template_id,
                    "target_relpath": target,
                }
            )

    selector_prompt_rows: list[dict[str, str]] = []
    selector_error_reason: str | None = None
    selected_candidates: list[dict[str, str]]
    if bool(llm_selector_cfg.get("enabled_b", False)):
        selected_candidates, selector_prompt_rows, selector_error_reason = _select_with_llm_selector(
            selector_cfg=llm_selector_cfg,
            candidates=planned_candidates,
            allowed_targets=allowed_targets,
            allowed_templates=allowed_templates,
            max_ccaps=max_ccaps,
            latest_observation=latest_observation,
        )
    else:
        selected_candidates = list(planned_candidates[:max_ccaps])

    prompt_rows = [*trace_prompt_rows, *selector_prompt_rows]
    prompt_hashes = [str(row.get("prompt_hash", "")) for row in prompt_rows]
    fingerprint_inputs = {
        "schema_version": "ge_run_inputs_fingerprint_inputs_v2",
        "seed": seed,
        "model_id": model_id,
        "prompt_hashes": prompt_hashes,
        "prompt_response_rows": prompt_rows,
        "ge_config_id": str(ge_config.get("ge_config_id", "")),
        "authority_pins_hash": authority_pins_hash,
        "receipt_stream_hash": str(xs_snapshot.get("receipt_stream_hash", "")),
        "xs_id": str(xs_snapshot.get("xs_id", "")),
        "skill_policy_hash": skill_policy_hash,
    }
    inputs_hash = _sha256_prefixed(canon_bytes(fingerprint_inputs))

    fingerprint = {
        "schema_version": "ge_run_inputs_fingerprint_v2",
        "inputs_hash": inputs_hash,
        "seed": seed,
        "model_id": model_id,
        "prompt_hashes": prompt_hashes,
        "prompt_response_rows": prompt_rows,
        "ge_config_id": str(ge_config.get("ge_config_id", "")),
        "authority_pins_hash": authority_pins_hash,
        "receipt_stream_hash": str(xs_snapshot.get("receipt_stream_hash", "")),
        "xs_id": str(xs_snapshot.get("xs_id", "")),
        "skill_policy_hash": skill_policy_hash,
    }
    _write_json(subrun_out_dir / "ge_run_inputs_fingerprint_v2.json", fingerprint)

    if prompt_rows:
        _write_json(
            subrun_out_dir / "ge_prompt_response_hashes_v1.json",
            {
                "schema_version": "ge_prompt_response_hashes_v1",
                "inputs_hash": inputs_hash,
                "rows": prompt_rows,
            },
        )

    diagnostic_reason_code: str | None = None
    if bool(skill_policy.get("persistence_unhealthy_b", False)):
        diagnostic_reason_code = "PERSISTENCE_HEALTH_DROP"
    elif selector_error_reason is not None:
        diagnostic_reason_code = str(selector_error_reason)

    emitted_ccaps: list[dict[str, Any]] = []
    global_slot = 0
    diagnostic_only_b = diagnostic_reason_code is not None
    if diagnostic_only_b:
        _write_json(
            subrun_out_dir / "ge_diagnostic_only_v1.json",
            {
                "schema_version": "ge_diagnostic_only_v1",
                "inputs_hash": inputs_hash,
                "skill_policy_hash": skill_policy_hash,
                "reason_code": str(diagnostic_reason_code),
                "bucket_plan": {
                    "opt_u64": int(bucket_plan["opt"]),
                    "nov_u64": int(bucket_plan["nov"]),
                    "grow_u64": int(bucket_plan["grow"]),
                },
                "ccap_count_u64": 0,
            },
        )
    else:
        for row in selected_candidates:
            bucket = str(row.get("bucket", "")).strip()
            template_id = str(row.get("template_id", "")).strip()
            target = _normalize_relpath(str(row.get("target_relpath", "")).strip())
            marker = f"{bucket}_{seed:016x}_{global_slot:04d}_{inputs_hash.split(':', 1)[1][:12]}"
            emitted_ccaps.append(
                _emit_ccap(
                    repo_root=repo_root,
                    out_dir=subrun_out_dir,
                    pins=pins,
                    active_ek=active_ek,
                    auth_hash_value=auth_hash_value,
                    build_recipe_id=build_recipe_id,
                    base_tree_id=base_tree_id,
                    target_relpath=target,
                    marker=marker,
                    size_buckets_bytes_u64=size_buckets_u64,
                    bucket=bucket,
                    template_id=template_id,
                )
            )
            global_slot += 1

    summary = {
        "schema_version": "ge_symbiotic_optimizer_summary_v0_3",
        "inputs_hash": inputs_hash,
        "auth_hash": auth_hash_value,
        "ge_config_id": str(ge_config.get("ge_config_id", "")),
        "skill_policy_hash": skill_policy_hash,
        "skill_policy_mode": str(skill_policy.get("mode", "DEFAULT")),
        "skill_policy": skill_policy,
        "bucket_plan": {
            "opt_u64": int(bucket_plan["opt"]),
            "nov_u64": int(bucket_plan["nov"]),
            "grow_u64": int(bucket_plan["grow"]),
        },
        "diagnostic_only_b": bool(diagnostic_only_b),
        "ccaps": emitted_ccaps,
    }
    _write_json(subrun_out_dir / "ge_symbiotic_optimizer_summary_v0_3.json", summary)

    print(
        json.dumps(
            {
                "status": "OK",
                "inputs_hash": inputs_hash,
                "ccap_count_u64": len(emitted_ccaps),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
