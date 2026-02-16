#!/usr/bin/env python3
"""Untrusted LLM router with replayable tool-use (v1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from tools.polymath.polymath_websearch_v1 import duckduckgo_search, wikipedia_search

_LLM_REPLAY_SCHEMA_VERSION = "orch_llm_replay_row_v1"
_ROUTER_PLAN_SCHEMA_VERSION = "omega_llm_router_plan_v1"
_ROUTER_TRACE_SCHEMA_VERSION = "omega_llm_tool_trace_row_v1"
_ROUTER_PROMPT_SCHEMA_VERSION = "omega_llm_router_prompt_v1"

_ALLOWED_PROVIDERS = {"duckduckgo", "wikipedia"}
_MAX_WEB_QUERIES_U64 = 4
_MAX_GOAL_INJECTIONS_U64 = 8
_MAX_QUERY_CHARS_U64 = 200
_MAX_REASON_CHARS_U64 = 512
_MAX_GOAL_ID_CHARS_U64 = 120
_MAX_TOP_K_U64 = 10
_DEFAULT_TOP_K_U64 = 5
_DEFAULT_MAX_CALLS_U64 = 64
_DEFAULT_MAX_PROMPT_CHARS_U64 = 12000
_DEFAULT_MAX_RESPONSE_CHARS_U64 = 16000
_DEFAULT_MAX_TOKENS_U64 = 1200
_DEFAULT_TEMPERATURE_STRICT_F64 = 0.0
_DEFAULT_TEMPERATURE_WILD_F64 = 0.7


class _LLMReplayMissError(RuntimeError):
    pass


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def _trace_rows_count(path: Path) -> int:
    if not path.exists() or not path.is_file():
        return 0
    count = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            count += 1
    return count


def _int_env(name: str, default: int, *, minimum: int = 0) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return int(default)
    try:
        value = int(raw)
    except Exception:  # noqa: BLE001
        return int(default)
    return max(int(minimum), int(value))


def _float_env(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return float(default)
    try:
        value = float(raw)
    except Exception:  # noqa: BLE001
        return float(default)
    return float(max(float(minimum), min(float(maximum), float(value))))


def _optional_float_env(name: str, *, minimum: float, maximum: float) -> float | None:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except Exception:  # noqa: BLE001
        return None
    return float(max(float(minimum), min(float(maximum), float(value))))


def _default_temperature_f64() -> float:
    wild_mode = str(os.environ.get("OMEGA_WILD_MODE", "")).strip().lower() in {"1", "true", "yes", "on"}
    blackbox_mode = str(os.environ.get("OMEGA_BLACKBOX", "")).strip().lower() in {"1", "true", "yes", "on"}
    if wild_mode or blackbox_mode:
        return float(_DEFAULT_TEMPERATURE_WILD_F64)
    return float(_DEFAULT_TEMPERATURE_STRICT_F64)


def _llm_generation_knobs() -> dict[str, Any]:
    return {
        "temperature_f64": float(
            _float_env(
                "ORCH_LLM_TEMPERATURE",
                _default_temperature_f64(),
                minimum=0.0,
                maximum=2.0,
            )
        ),
        "max_tokens_u64": int(
            _int_env(
                "ORCH_LLM_MAX_TOKENS",
                _DEFAULT_MAX_TOKENS_U64,
                minimum=1,
            )
        ),
        "top_p_f64": _optional_float_env("ORCH_LLM_TOP_P", minimum=0.0, maximum=1.0),
    }


def _validate_openai_model(model_id: str) -> str:
    value = str(model_id).strip()
    if not value.startswith(("gpt-", "o1", "o3", "o4")):
        raise RuntimeError("SCHEMA_FAIL")
    return value


def _validate_anthropic_model(model_id: str) -> str:
    value = str(model_id).strip()
    if not value.startswith("claude-"):
        raise RuntimeError("SCHEMA_FAIL")
    return value


def _validate_gemini_model(model_id: str) -> str:
    value = str(model_id).strip()
    if not value.startswith("gemini-"):
        raise RuntimeError("SCHEMA_FAIL")
    return value


def _http_post_json(*, url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    req = Request(url=url, data=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"), method="POST")
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
        raise RuntimeError("SCHEMA_FAIL")
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


def _extract_gemini_response_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise RuntimeError("LLM_RESPONSE_EMPTY")
    chunks: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
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
    if not replay_path.exists() or not replay_path.is_file():
        raise _LLMReplayMissError("LLM_REPLAY_MISS")
    prompt_hash = _sha256_prefixed(prompt.encode("utf-8"))
    for line in replay_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            continue
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
            raise RuntimeError("SCHEMA_FAIL")
        if str(payload.get("response_sha256", "")).strip() != _sha256_prefixed(response.encode("utf-8")):
            raise RuntimeError("SCHEMA_FAIL")
        return response
    raise _LLMReplayMissError("LLM_REPLAY_MISS")


def _lookup_replay_response_any(*, replay_path: Path, prompt: str) -> tuple[str, str, str]:
    if not replay_path.exists() or not replay_path.is_file():
        raise _LLMReplayMissError("LLM_REPLAY_MISS")
    prompt_hash = _sha256_prefixed(prompt.encode("utf-8"))
    for line in replay_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            continue
        if str(payload.get("schema_version", "")).strip() != _LLM_REPLAY_SCHEMA_VERSION:
            continue
        if str(payload.get("prompt_sha256", "")).strip() != prompt_hash:
            continue
        response = payload.get("response")
        if not isinstance(response, str):
            raise RuntimeError("SCHEMA_FAIL")
        if str(payload.get("response_sha256", "")).strip() != _sha256_prefixed(response.encode("utf-8")):
            raise RuntimeError("SCHEMA_FAIL")
        backend = str(payload.get("backend", "")).strip() or "replay"
        model = str(payload.get("model", "")).strip() or "replay"
        return response, backend, model
    raise _LLMReplayMissError("LLM_REPLAY_MISS")


def _router_backend_response(*, backend: str, prompt: str) -> tuple[str, str, str, str, dict[str, Any]]:
    backend_key_raw = str(backend).strip()
    backend_aliases = {
        "openai": "openai_harvest",
        "anthropic": "anthropic_harvest",
        "google": "gemini_harvest",
        "gemini": "gemini_harvest",
    }
    backend_key = backend_aliases.get(backend_key_raw, backend_key_raw)
    generation_knobs = _llm_generation_knobs()
    replay_path_raw = str(os.environ.get("ORCH_LLM_REPLAY_PATH", "")).strip()
    replay_path = Path(replay_path_raw).expanduser().resolve() if replay_path_raw else None

    if backend_key == "mock":
        mode = str(os.environ.get("ORCH_LLM_MOCK_MODE", "")).strip().lower()
        if mode == "empty":
            response = ""
        else:
            response = str(
                os.environ.get(
                    "ORCH_LLM_MOCK_RESPONSE",
                    json.dumps(
                        {
                            "schema_version": _ROUTER_PLAN_SCHEMA_VERSION,
                            "created_at_utc": "",
                            "created_from_tick_u64": 0,
                            "web_queries": [],
                            "goal_injections": [],
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
            )
        return response, "mock", "mock", backend_key, generation_knobs

    if backend_key == "replay":
        if replay_path is None:
            raise RuntimeError("LLM_REPLAY_PATH_MISSING")
        response, provider, model = _lookup_replay_response_any(replay_path=replay_path, prompt=prompt)
        return response, provider, model, backend_key, generation_knobs

    if backend_key in {"openai_replay", "openai_harvest"}:
        provider = "openai"
        model = _validate_openai_model(str(os.environ.get("ORCH_OPENAI_MODEL", "gpt-4.1")))
    elif backend_key in {"anthropic_replay", "anthropic_harvest"}:
        provider = "anthropic"
        model = _validate_anthropic_model(str(os.environ.get("ORCH_ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")))
    elif backend_key in {"gemini_replay", "gemini_harvest"}:
        provider = "gemini"
        model = _validate_gemini_model(str(os.environ.get("ORCH_GEMINI_MODEL", "gemini-2.0-flash")))
    else:
        raise RuntimeError("LLM_BACKEND_UNSUPPORTED")

    if replay_path is None:
        raise RuntimeError("LLM_REPLAY_PATH_MISSING")

    if backend_key.endswith("_replay"):
        response = _lookup_replay_response(replay_path=replay_path, provider=provider, model=model, prompt=prompt)
        return response, provider, model, backend_key, generation_knobs

    if str(os.environ.get("ORCH_LLM_LIVE_OK", "")).strip() != "1":
        raise RuntimeError("LLM_LIVE_DISABLED")

    if provider == "openai":
        api_key = str(os.environ.get("OPENAI_API_KEY", "")).strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY_MISSING")
        request_payload = {
            "model": model,
            "input": prompt,
            "temperature": float(generation_knobs.get("temperature_f64", _DEFAULT_TEMPERATURE_STRICT_F64)),
            "max_output_tokens": int(generation_knobs.get("max_tokens_u64", _DEFAULT_MAX_TOKENS_U64)),
        }
        top_p = generation_knobs.get("top_p_f64")
        if top_p is not None:
            request_payload["top_p"] = float(top_p)
        raw_payload = _http_post_json(
            url="https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}"},
            payload=request_payload,
        )
        response = _extract_openai_response_text(raw_payload)
    elif provider == "anthropic":
        api_key = str(os.environ.get("ANTHROPIC_API_KEY", "")).strip()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY_MISSING")
        version = str(os.environ.get("ORCH_ANTHROPIC_VERSION", "2023-06-01")).strip() or "2023-06-01"
        request_payload = {
            "model": model,
            "max_tokens": int(generation_knobs.get("max_tokens_u64", _DEFAULT_MAX_TOKENS_U64)),
            "temperature": float(generation_knobs.get("temperature_f64", _DEFAULT_TEMPERATURE_STRICT_F64)),
            "messages": [{"role": "user", "content": prompt}],
        }
        top_p = generation_knobs.get("top_p_f64")
        if top_p is not None:
            request_payload["top_p"] = float(top_p)
        raw_payload = _http_post_json(
            url="https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": version},
            payload=request_payload,
        )
        response = _extract_anthropic_response_text(raw_payload)
    else:
        api_key = str(os.environ.get("GOOGLE_API_KEY", "")).strip()
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY_MISSING")
        generation_config = {
            "temperature": float(generation_knobs.get("temperature_f64", _DEFAULT_TEMPERATURE_STRICT_F64)),
            "maxOutputTokens": int(generation_knobs.get("max_tokens_u64", _DEFAULT_MAX_TOKENS_U64)),
        }
        top_p = generation_knobs.get("top_p_f64")
        if top_p is not None:
            generation_config["topP"] = float(top_p)
        raw_payload = _http_post_json(
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            headers={},
            payload={
                "generationConfig": generation_config,
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}],
                    }
                ],
            },
        )
        response = _extract_gemini_response_text(raw_payload)

    replay_row = {
        "schema_version": _LLM_REPLAY_SCHEMA_VERSION,
        "backend": provider,
        "model": model,
        "prompt_sha256": _sha256_prefixed(prompt.encode("utf-8")),
        "response_sha256": _sha256_prefixed(response.encode("utf-8")),
        "prompt": prompt,
        "response": response,
        "created_at_utc": _utc_now_iso(),
        "raw_response_json": raw_payload,
        "generation_knobs": generation_knobs,
    }
    _append_replay_row(replay_path, replay_row)
    return response, provider, model, backend_key, generation_knobs


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = _read_json(path)
    except Exception:  # noqa: BLE001
        return {}
    return payload


def _load_registry_allowlists(run_dir: Path) -> dict[str, Any]:
    registry_path = run_dir / "_overnight_pack" / "omega_capability_registry_v2.json"
    payload = _load_optional_json(registry_path)
    caps = payload.get("capabilities") if isinstance(payload, dict) else None
    campaign_ids: list[str] = []
    capability_ids: list[str] = []
    cap_to_campaign: dict[str, str] = {}
    if isinstance(caps, list):
        for row in caps:
            if not isinstance(row, dict):
                continue
            if not bool(row.get("enabled", False)):
                continue
            campaign_id = str(row.get("campaign_id", "")).strip()
            capability_id = str(row.get("capability_id", "")).strip()
            if campaign_id:
                campaign_ids.append(campaign_id)
            if capability_id:
                capability_ids.append(capability_id)
                cap_to_campaign[capability_id] = campaign_id
    return {
        "registry_path": registry_path.as_posix(),
        "allowed_campaign_ids": sorted(set(campaign_ids)),
        "allowed_capability_ids": sorted(set(capability_ids)),
        "capability_to_campaign": {key: cap_to_campaign[key] for key in sorted(cap_to_campaign.keys())},
    }


def _project_benchmark_gates(payload: dict[str, Any]) -> dict[str, Any]:
    gates = payload.get("gates") if isinstance(payload, dict) else None
    out: dict[str, str] = {}
    if isinstance(gates, dict):
        for gate in sorted(gates.keys()):
            row = gates.get(gate)
            if not isinstance(row, dict):
                continue
            status = str(row.get("status", "")).strip()
            if status:
                out[str(gate)] = status
    return {
        "schema_version": str(payload.get("schema_version", "")) if isinstance(payload, dict) else "",
        "gate_status": out,
    }


def _project_promotion_summary(payload: dict[str, Any]) -> dict[str, Any]:
    out = {
        "schema_version": str(payload.get("schema_version", "")),
        "promoted_u64": int(payload.get("promoted_u64", 0)) if isinstance(payload, dict) else 0,
        "activation_success_u64": int(payload.get("activation_success_u64", 0)) if isinstance(payload, dict) else 0,
        "unique_promotions_u64": int(payload.get("unique_promotions_u64", 0)) if isinstance(payload, dict) else 0,
    }
    return out


def _project_capability_usage(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    usage = payload.get("capabilities")
    top_rows: list[dict[str, Any]] = []
    if isinstance(usage, list):
        rows: list[dict[str, Any]] = []
        for row in usage:
            if not isinstance(row, dict):
                continue
            capability_id = str(row.get("capability_id", "")).strip()
            dispatches_u64 = int(row.get("dispatches_u64", 0))
            if not capability_id:
                continue
            rows.append({"capability_id": capability_id, "dispatches_u64": dispatches_u64})
        rows.sort(key=lambda row: (-int(row.get("dispatches_u64", 0)), str(row.get("capability_id", ""))))
        top_rows = rows[:20]
    return {
        "schema_version": str(payload.get("schema_version", "")),
        "top_capability_dispatches": top_rows,
    }


def _prompt_payload(*, run_dir: Path, tick_u64: int, allowlists: dict[str, Any]) -> dict[str, Any]:
    benchmark_payload = _project_benchmark_gates(_load_optional_json(run_dir / "OMEGA_BENCHMARK_GATES_v1.json"))
    promotion_payload = _project_promotion_summary(_load_optional_json(run_dir / "OMEGA_PROMOTION_SUMMARY_v1.json"))
    capability_usage_payload = _project_capability_usage(_load_optional_json(run_dir / "OMEGA_CAPABILITY_USAGE_v1.json"))
    return {
        "schema_version": _ROUTER_PROMPT_SCHEMA_VERSION,
        "task": "Return ONLY raw JSON (no markdown, no code fences, no commentary). Propose bounded web queries and goal injections.",
        "created_from_tick_u64": int(max(0, int(tick_u64))),
        "benchmark_gates": benchmark_payload,
        "promotion_summary": promotion_payload,
        "capability_usage": capability_usage_payload,
        "allowed_campaign_ids": list(allowlists.get("allowed_campaign_ids", [])),
        "allowed_goal_capability_ids": list(allowlists.get("allowed_capability_ids", [])),
        "limits": {
            "max_web_queries_u64": int(_MAX_WEB_QUERIES_U64),
            "max_goal_injections_u64": int(_MAX_GOAL_INJECTIONS_U64),
            "max_query_chars_u64": int(_MAX_QUERY_CHARS_U64),
            "max_top_k_u64": int(_MAX_TOP_K_U64),
        },
        "required_output_json": {
            "schema_version": _ROUTER_PLAN_SCHEMA_VERSION,
            "created_at_utc": "",
            "created_from_tick_u64": int(max(0, int(tick_u64))),
            "web_queries": [{"provider": "duckduckgo|wikipedia", "query": "...", "top_k": 5}],
            "goal_injections": [
                {
                    "capability_id": "RSI_SAS_METASEARCH",
                    "goal_id": "goal_auto_...",
                    "priority_u8": 5,
                    "reason": "...",
                }
            ],
        },
    }


def _normalize_plan(
    *,
    response_text: str,
    tick_u64: int,
    allowed_capability_ids: set[str],
) -> dict[str, Any]:
    def _strip_outer_code_fence(text: str) -> str:
        # Deterministic: Gemini frequently wraps JSON in ```json ... ``` fences.
        s = str(text or "").strip()
        if not s.startswith("```"):
            return s
        first_nl = s.find("\n")
        if first_nl < 0:
            return s
        last_fence = s.rfind("```")
        if last_fence <= first_nl:
            return s
        return s[first_nl + 1 : last_fence].strip()

    def _extract_json_dict(text: str) -> dict[str, Any]:
        s = _strip_outer_code_fence(text)
        try:
            obj = json.loads(s)
        except Exception:  # noqa: BLE001
            # Fall back to parsing the first full {...} block.
            start = s.find("{")
            end = s.rfind("}")
            if start < 0 or end < 0 or end <= start:
                raise
            obj = json.loads(s[start : end + 1])
        if not isinstance(obj, dict):
            raise RuntimeError("LLM_ROUTER_INVALID_JSON")
        # Common failure mode: return {"required_output_json": {...}} even though we asked for the inner object.
        inner = obj.get("required_output_json")
        if isinstance(inner, dict):
            return inner
        return obj

    try:
        payload = _extract_json_dict(response_text)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("LLM_ROUTER_INVALID_JSON") from exc

    rejected_web_queries: list[dict[str, str]] = []
    rejected_goal_injections: list[dict[str, str]] = []

    web_rows = payload.get("web_queries")
    parsed_web_queries: list[dict[str, Any]] = []
    if isinstance(web_rows, list):
        for row in web_rows:
            if not isinstance(row, dict):
                continue
            provider = str(row.get("provider", "")).strip().lower()
            if provider not in _ALLOWED_PROVIDERS:
                rejected_web_queries.append({"provider": provider, "reason": "UNKNOWN_PROVIDER"})
                continue
            query = " ".join(str(row.get("query", "")).strip().split())
            if not query:
                rejected_web_queries.append({"provider": provider, "reason": "EMPTY_QUERY"})
                continue
            if len(query) > _MAX_QUERY_CHARS_U64:
                rejected_web_queries.append({"provider": provider, "reason": "QUERY_TOO_LONG"})
                continue
            top_k = int(row.get("top_k", _DEFAULT_TOP_K_U64))
            top_k = max(1, min(_MAX_TOP_K_U64, top_k))
            parsed_web_queries.append({"provider": provider, "query": query, "top_k": int(top_k)})

    parsed_web_queries.sort(key=lambda row: (str(row["provider"]), str(row["query"]), int(row["top_k"])))
    kept_web_queries = parsed_web_queries[:_MAX_WEB_QUERIES_U64]
    for row in parsed_web_queries[_MAX_WEB_QUERIES_U64:]:
        rejected_web_queries.append(
            {
                "provider": str(row.get("provider", "")),
                "query": str(row.get("query", "")),
                "reason": "MAX_WEB_QUERIES_EXCEEDED",
            }
        )

    goal_rows = payload.get("goal_injections")
    parsed_goal_injections: list[dict[str, Any]] = []
    if isinstance(goal_rows, list):
        for row in goal_rows:
            if not isinstance(row, dict):
                continue
            capability_id = str(row.get("capability_id", "")).strip()
            if not capability_id:
                rejected_goal_injections.append({"reason": "EMPTY_CAPABILITY_ID"})
                continue
            if capability_id not in allowed_capability_ids:
                rejected_goal_injections.append(
                    {
                        "capability_id": capability_id,
                        "reason": "CAPABILITY_NOT_ENABLED",
                    }
                )
                continue
            goal_id = " ".join(str(row.get("goal_id", "")).strip().split())
            if not goal_id:
                rejected_goal_injections.append(
                    {
                        "capability_id": capability_id,
                        "reason": "EMPTY_GOAL_ID",
                    }
                )
                continue
            if len(goal_id) > _MAX_GOAL_ID_CHARS_U64:
                rejected_goal_injections.append(
                    {
                        "capability_id": capability_id,
                        "goal_id": goal_id,
                        "reason": "GOAL_ID_TOO_LONG",
                    }
                )
                continue
            priority_u8 = int(row.get("priority_u8", 0))
            priority_u8 = max(0, min(255, priority_u8))
            reason = " ".join(str(row.get("reason", "")).strip().split())
            reason = reason[:_MAX_REASON_CHARS_U64]
            parsed_goal_injections.append(
                {
                    "capability_id": capability_id,
                    "goal_id": goal_id,
                    "priority_u8": int(priority_u8),
                    "reason": reason,
                }
            )

    parsed_goal_injections.sort(
        key=lambda row: (
            -int(row.get("priority_u8", 0)),
            str(row.get("capability_id", "")),
            str(row.get("goal_id", "")),
        )
    )
    kept_goal_injections = parsed_goal_injections[:_MAX_GOAL_INJECTIONS_U64]
    for row in parsed_goal_injections[_MAX_GOAL_INJECTIONS_U64:]:
        rejected_goal_injections.append(
            {
                "capability_id": str(row.get("capability_id", "")),
                "goal_id": str(row.get("goal_id", "")),
                "reason": "MAX_GOAL_INJECTIONS_EXCEEDED",
            }
        )

    return {
        "schema_version": _ROUTER_PLAN_SCHEMA_VERSION,
        "created_at_utc": "",
        "created_from_tick_u64": int(max(0, int(tick_u64))),
        "web_queries": kept_web_queries,
        "goal_injections": kept_goal_injections,
        "rejected_web_queries": sorted(
            rejected_web_queries,
            key=lambda row: (
                str(row.get("reason", "")),
                str(row.get("provider", "")),
                str(row.get("query", "")),
            ),
        ),
        "rejected_goal_injections": sorted(
            rejected_goal_injections,
            key=lambda row: (
                str(row.get("reason", "")),
                str(row.get("capability_id", "")),
                str(row.get("goal_id", "")),
            ),
        ),
    }


def _execute_web_queries(*, plan: dict[str, Any], store_root: Path | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    executed: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    rows = plan.get("web_queries")
    if not isinstance(rows, list):
        return executed, tool_calls

    for row in rows:
        if not isinstance(row, dict):
            continue
        provider = str(row.get("provider", "")).strip().lower()
        query = str(row.get("query", "")).strip()
        top_k = max(1, min(_MAX_TOP_K_U64, int(row.get("top_k", _DEFAULT_TOP_K_U64))))
        call_trace = {
            "tool": f"websearch.{provider}",
            "provider": provider,
            "query": query,
            "top_k": int(top_k),
            "status": "ERROR",
            "sealed_sha256": "",
            "sealed_receipt_path": "",
            "error": "",
        }
        try:
            if provider == "duckduckgo":
                result = duckduckgo_search(query=query, top_k=top_k, store_root=store_root)
            elif provider == "wikipedia":
                result = wikipedia_search(query=query, top_k=top_k, store_root=store_root)
            else:
                raise RuntimeError("UNKNOWN_PROVIDER")
            sealed = result.get("sealed") if isinstance(result, dict) else None
            summary = result.get("summary") if isinstance(result, dict) else None
            if not isinstance(sealed, dict) or not isinstance(summary, dict):
                raise RuntimeError("TOOL_RESULT_INVALID")
            call_trace["status"] = "OK"
            call_trace["sealed_sha256"] = str(sealed.get("sha256", ""))
            call_trace["sealed_receipt_path"] = str(sealed.get("receipt_path", ""))
            executed.append(
                {
                    "provider": provider,
                    "query": query,
                    "top_k": int(top_k),
                    "sealed": {
                        "url": str(sealed.get("url", "")),
                        "sha256": str(sealed.get("sha256", "")),
                        "receipt_path": str(sealed.get("receipt_path", "")),
                        "bytes_path": str(sealed.get("bytes_path", "")),
                        "cached_b": bool(sealed.get("cached_b", False)),
                    },
                    "summary": summary,
                }
            )
        except Exception as exc:  # noqa: BLE001
            call_trace["error"] = str(exc)
            executed.append(
                {
                    "provider": provider,
                    "query": query,
                    "top_k": int(top_k),
                    "error": str(exc),
                }
            )
        tool_calls.append(call_trace)
    return executed, tool_calls


def run(*, run_dir: Path, tick_u64: int, store_root: Path | None = None) -> dict[str, Any]:
    run_root = run_dir.resolve()
    plan_path = run_root / "OMEGA_LLM_ROUTER_PLAN_v1.json"
    trace_path = run_root / "OMEGA_LLM_TOOL_TRACE_v1.jsonl"

    max_calls_u64 = _int_env("ORCH_LLM_MAX_CALLS", _DEFAULT_MAX_CALLS_U64, minimum=1)
    if _trace_rows_count(trace_path) >= int(max_calls_u64):
        raise RuntimeError("LLM_CALL_BUDGET_EXCEEDED")

    allowlists = _load_registry_allowlists(run_root)
    prompt_payload = _prompt_payload(run_dir=run_root, tick_u64=int(tick_u64), allowlists=allowlists)
    prompt = json.dumps(prompt_payload, sort_keys=True, separators=(",", ":"))

    max_prompt_chars_u64 = _int_env("ORCH_LLM_MAX_PROMPT_CHARS", _DEFAULT_MAX_PROMPT_CHARS_U64, minimum=1)
    if len(prompt) > int(max_prompt_chars_u64):
        raise RuntimeError("LLM_PROMPT_TOO_LARGE")

    backend = str(os.environ.get("ORCH_LLM_BACKEND", "mock")).strip() or "mock"
    response_text, provider, model, backend_used, generation_knobs = _router_backend_response(backend=backend, prompt=prompt)

    max_response_chars_u64 = _int_env("ORCH_LLM_MAX_RESPONSE_CHARS", _DEFAULT_MAX_RESPONSE_CHARS_U64, minimum=1)
    if len(response_text) > int(max_response_chars_u64):
        raise RuntimeError("LLM_RESPONSE_TOO_LARGE")

    normalized = _normalize_plan(
        response_text=response_text,
        tick_u64=int(tick_u64),
        allowed_capability_ids=set(str(row) for row in allowlists.get("allowed_capability_ids", [])),
    )
    executed_web_queries, tool_calls = _execute_web_queries(plan=normalized, store_root=store_root)

    final_plan = {
        "schema_version": _ROUTER_PLAN_SCHEMA_VERSION,
        "created_at_utc": "",
        "created_from_tick_u64": int(max(0, int(tick_u64))),
        "web_queries": executed_web_queries,
        "goal_injections": normalized.get("goal_injections", []),
        "diagnostics": {
            "backend": backend_used,
            "provider": provider,
            "model": model,
            "prompt_sha256": _sha256_prefixed(prompt.encode("utf-8")),
            "response_sha256": _sha256_prefixed(response_text.encode("utf-8")),
            "registry_path": str(allowlists.get("registry_path", "")),
            "allowed_campaign_ids": list(allowlists.get("allowed_campaign_ids", [])),
            "allowed_capability_ids": list(allowlists.get("allowed_capability_ids", [])),
            "rejected_web_queries": list(normalized.get("rejected_web_queries", [])),
            "rejected_goal_injections": list(normalized.get("rejected_goal_injections", [])),
            "llm_temperature_f64": float(generation_knobs.get("temperature_f64", _DEFAULT_TEMPERATURE_STRICT_F64)),
            "llm_max_tokens_u64": int(generation_knobs.get("max_tokens_u64", _DEFAULT_MAX_TOKENS_U64)),
            "llm_top_p_f64": generation_knobs.get("top_p_f64"),
        },
    }
    _write_json(plan_path, final_plan)

    trace_row = {
        "schema_version": _ROUTER_TRACE_SCHEMA_VERSION,
        "created_at_utc": "",
        "created_from_tick_u64": int(max(0, int(tick_u64))),
        "tick_u64": int(max(0, int(tick_u64))),
        "backend": backend_used,
        "provider": provider,
        "model": model,
        "prompt_sha256": _sha256_prefixed(prompt.encode("utf-8")),
        "response_sha256": _sha256_prefixed(response_text.encode("utf-8")),
        "tool_calls": tool_calls,
        "goal_injections_requested_u64": int(len(normalized.get("goal_injections", []))),
        "goal_injections_accepted_u64": int(len(normalized.get("goal_injections", []))),
        "llm_temperature_f64": float(generation_knobs.get("temperature_f64", _DEFAULT_TEMPERATURE_STRICT_F64)),
        "llm_max_tokens_u64": int(generation_knobs.get("max_tokens_u64", _DEFAULT_MAX_TOKENS_U64)),
        "llm_top_p_f64": generation_knobs.get("top_p_f64"),
        "error": "",
    }
    _append_jsonl(trace_path, trace_row)

    return {
        "status": "OK",
        "plan_path": plan_path.as_posix(),
        "trace_path": trace_path.as_posix(),
        "goal_injections": list(normalized.get("goal_injections", [])),
        "web_queries": executed_web_queries,
        "prompt_sha256": trace_row["prompt_sha256"],
        "response_sha256": trace_row["response_sha256"],
        "backend": backend_used,
        "provider": provider,
        "model": model,
        "llm_temperature_f64": float(generation_knobs.get("temperature_f64", _DEFAULT_TEMPERATURE_STRICT_F64)),
        "llm_max_tokens_u64": int(generation_knobs.get("max_tokens_u64", _DEFAULT_MAX_TOKENS_U64)),
        "llm_top_p_f64": generation_knobs.get("top_p_f64"),
    }


def run_failsoft(*, run_dir: Path, tick_u64: int, store_root: Path | None = None) -> dict[str, Any]:
    run_root = run_dir.resolve()
    plan_path = run_root / "OMEGA_LLM_ROUTER_PLAN_v1.json"
    trace_path = run_root / "OMEGA_LLM_TOOL_TRACE_v1.jsonl"
    generation_knobs = _llm_generation_knobs()
    try:
        return run(run_dir=run_root, tick_u64=tick_u64, store_root=store_root)
    except _LLMReplayMissError as exc:
        error_reason = str(exc) or "LLM_REPLAY_MISS"
    except Exception as exc:  # noqa: BLE001
        error_reason = str(exc)

    fallback_plan = {
        "schema_version": _ROUTER_PLAN_SCHEMA_VERSION,
        "created_at_utc": "",
        "created_from_tick_u64": int(max(0, int(tick_u64))),
        "web_queries": [],
        "goal_injections": [],
        "diagnostics": {
            "error_reason": error_reason,
            "llm_temperature_f64": float(generation_knobs.get("temperature_f64", _DEFAULT_TEMPERATURE_STRICT_F64)),
            "llm_max_tokens_u64": int(generation_knobs.get("max_tokens_u64", _DEFAULT_MAX_TOKENS_U64)),
            "llm_top_p_f64": generation_knobs.get("top_p_f64"),
        },
    }
    _write_json(plan_path, fallback_plan)
    _append_jsonl(
        trace_path,
        {
            "schema_version": _ROUTER_TRACE_SCHEMA_VERSION,
            "created_at_utc": "",
            "created_from_tick_u64": int(max(0, int(tick_u64))),
            "tick_u64": int(max(0, int(tick_u64))),
            "backend": str(os.environ.get("ORCH_LLM_BACKEND", "mock")).strip() or "mock",
            "provider": "",
            "model": "",
            "prompt_sha256": "",
            "response_sha256": "",
            "tool_calls": [],
            "goal_injections_requested_u64": 0,
            "goal_injections_accepted_u64": 0,
            "llm_temperature_f64": float(generation_knobs.get("temperature_f64", _DEFAULT_TEMPERATURE_STRICT_F64)),
            "llm_max_tokens_u64": int(generation_knobs.get("max_tokens_u64", _DEFAULT_MAX_TOKENS_U64)),
            "llm_top_p_f64": generation_knobs.get("top_p_f64"),
            "error": error_reason,
        },
    )
    return {
        "status": "ERROR",
        "error_reason": error_reason,
        "plan_path": plan_path.as_posix(),
        "trace_path": trace_path.as_posix(),
        "goal_injections": [],
        "web_queries": [],
        "llm_temperature_f64": float(generation_knobs.get("temperature_f64", _DEFAULT_TEMPERATURE_STRICT_F64)),
        "llm_max_tokens_u64": int(generation_knobs.get("max_tokens_u64", _DEFAULT_MAX_TOKENS_U64)),
        "llm_top_p_f64": generation_knobs.get("top_p_f64"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="omega_llm_router_v1")
    parser.add_argument("--run_dir", required=True)
    parser.add_argument("--tick_u64", type=int, required=True)
    parser.add_argument("--store_root", default="")
    parser.add_argument("--failsoft", type=int, default=1)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    store_root = Path(args.store_root).expanduser().resolve() if str(args.store_root).strip() else None
    if bool(int(args.failsoft)):
        payload = run_failsoft(run_dir=run_dir, tick_u64=max(0, int(args.tick_u64)), store_root=store_root)
    else:
        payload = run(run_dir=run_dir, tick_u64=max(0, int(args.tick_u64)), store_root=store_root)
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
