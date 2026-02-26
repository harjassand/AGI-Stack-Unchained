from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import json
import os
import time
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, Literal, Optional, Tuple

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from tools.mission_control.chat_router_v2 import decide_chat_route_v2
from tools.mission_control._signal_parse_v1 import map_trace_class, parse_signal_line
from tools.mission_control._state_discovery_v1 import (
    build_current_state_payload,
    discover_state_path_info,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGED_PATH = ".omega_cache/mission_staging/pending_mission.json"
_LOG_DISCOVERY_CACHE_TTL_S = 2.0
_LOG_DISCOVERY_CACHE: Dict[str, Any] = {"ts": 0.0, "path": None, "source": ""}
_RUNS_SCAN_MAX_DEPTH = 8
_RUNS_SCAN_PRUNE_DIRS = {
    ".git",
    "node_modules",
    ".next",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
}


app = FastAPI(title="Mission Control Stream Server v1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class MissionRequest(BaseModel):
    human_intent_str: str


class ChatRequest(BaseModel):
    message: str
    mode: Literal["customer", "dev"] = "customer"


def _now_unix_ms() -> int:
    return int(time.time() * 1000)


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return -1.0


def _scan_runs_for_latest_log(runs_root: Path) -> Optional[Path]:
    best_path: Optional[Path] = None
    best_mtime = -1.0

    for root, dirs, files in os.walk(runs_root, topdown=True, followlinks=False):
        try:
            rel_depth = len(Path(root).relative_to(runs_root).parts)
        except ValueError:
            rel_depth = 0

        kept_dirs = []
        for dirname in dirs:
            full = Path(root) / dirname
            if full.is_symlink():
                continue
            if dirname in _RUNS_SCAN_PRUNE_DIRS:
                continue
            kept_dirs.append(dirname)
        if rel_depth >= _RUNS_SCAN_MAX_DEPTH:
            dirs[:] = []
        else:
            dirs[:] = kept_dirs

        if "runaway_evolution.log" not in files:
            continue

        candidate = Path(root) / "runaway_evolution.log"
        if not candidate.is_file():
            continue
        candidate_mtime = _safe_mtime(candidate)
        if candidate_mtime >= best_mtime:
            best_mtime = candidate_mtime
            best_path = candidate

    return best_path


def _discover_log_path_info_uncached(repo_root: Path = REPO_ROOT) -> Tuple[Optional[Path], str]:
    env_path = os.getenv("MC_RUNAWAY_LOG_PATH")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.exists() and candidate.is_file():
            return candidate, "env"

    root_log = repo_root / "runaway_evolution.log"
    if root_log.exists() and root_log.is_file():
        return root_log, "root"

    runs_log = repo_root / "runs" / "runaway_evolution.log"
    if runs_log.exists() and runs_log.is_file():
        return runs_log, "runs"

    runs_root = repo_root / "runs"
    if runs_root.exists() and runs_root.is_dir():
        latest = _scan_runs_for_latest_log(runs_root)
        if latest is not None:
            return latest, "runs_scan"

    return None, ""


def _discover_log_path_info(repo_root: Path = REPO_ROOT) -> Tuple[Optional[Path], str]:
    now = time.monotonic()
    cached_ts = float(_LOG_DISCOVERY_CACHE.get("ts", 0.0))
    cached_path = _LOG_DISCOVERY_CACHE.get("path")
    cached_source = str(_LOG_DISCOVERY_CACHE.get("source", ""))
    if isinstance(cached_path, Path) and now - cached_ts < _LOG_DISCOVERY_CACHE_TTL_S:
        if cached_path.exists() and cached_path.is_file():
            return cached_path, cached_source
    if cached_path is None and now - cached_ts < _LOG_DISCOVERY_CACHE_TTL_S:
        return None, ""

    selected, source = _discover_log_path_info_uncached(repo_root=repo_root)
    _LOG_DISCOVERY_CACHE["ts"] = now
    _LOG_DISCOVERY_CACHE["path"] = selected
    _LOG_DISCOVERY_CACHE["source"] = source
    return selected, source


def _to_sse_data(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _build_event(
    *,
    seq: int,
    signal: str,
    tick_u64: int,
    raw_line: str,
    fields: Dict[str, str],
) -> Dict[str, Any]:
    return {
        "ts_unix_ms": _now_unix_ms(),
        "seq": seq,
        "trace_class": map_trace_class(signal),
        "signal": signal,
        "tick_u64": tick_u64,
        "raw_line": raw_line,
        "fields": fields,
    }


async def _stream_signal_events() -> AsyncIterator[str]:
    seq = 0
    file_handle = None
    active_path: Optional[Path] = None

    try:
        while True:
            selected_path, _source = _discover_log_path_info()
            if selected_path is None:
                payload = _build_event(
                    seq=seq,
                    signal="LOG_NOT_FOUND",
                    tick_u64=0,
                    raw_line="",
                    fields={},
                )
                yield _to_sse_data(payload)
                seq += 1
                await asyncio.sleep(2.0)
                continue

            if file_handle is None or selected_path != active_path:
                if file_handle is not None:
                    file_handle.close()
                file_handle = open(selected_path, "r", encoding="utf-8", errors="replace")
                file_handle.seek(0, os.SEEK_END)
                active_path = selected_path
                selected_abs = str(selected_path.resolve())
                payload = _build_event(
                    seq=seq,
                    signal="LOG_SOURCE_SELECTED",
                    tick_u64=0,
                    raw_line=f"SIGNAL=LOG_SOURCE_SELECTED path={selected_abs}",
                    fields={"path": selected_abs},
                )
                yield _to_sse_data(payload)
                seq += 1

            line = file_handle.readline()
            if not line:
                await asyncio.sleep(0.2)
                continue

            parsed = parse_signal_line(line)
            if parsed is None:
                continue

            payload = _build_event(
                seq=seq,
                signal=parsed.signal,
                tick_u64=parsed.tick_u64,
                raw_line=parsed.raw_line,
                fields=parsed.fields,
            )
            yield _to_sse_data(payload)
            seq += 1
    finally:
        if file_handle is not None:
            file_handle.close()


def _resolve_nlpmc_compiler() -> Optional[Callable[..., Any]]:
    try:
        module = importlib.import_module("tools.mission_control.nlpmc_v1")
    except Exception:
        return None
    compile_func = getattr(module, "compile_and_stage_mission", None)
    return compile_func if callable(compile_func) else None


def _nlpmc_not_available_response() -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"ok": False, "error": "NLPMC_NOT_AVAILABLE"},
    )


@app.get("/stream")
async def stream() -> StreamingResponse:
    return StreamingResponse(
        _stream_signal_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/api/state/current")
async def api_state_current() -> Dict[str, Any]:
    return build_current_state_payload(repo_root=REPO_ROOT)


@app.get("/api/health")
async def api_health() -> Dict[str, Any]:
    log_path, log_source = _discover_log_path_info(repo_root=REPO_ROOT)
    state_path, state_source = discover_state_path_info(repo_root=REPO_ROOT)

    log_found_b = log_path is not None
    state_found_b = state_path is not None

    return {
        "ok": True,
        "log": {
            "found_b": log_found_b,
            "selected_path": str(log_path.resolve()) if log_path else "",
            "source": log_source if log_found_b else "",
        },
        "state": {
            "found_b": state_found_b,
            "selected_path": str(state_path.resolve()) if state_path else "",
            "source": state_source if state_found_b else "",
        },
        "sse": {
            "synthetic_log_not_found_emitting_b": not log_found_b,
        },
    }


@app.post("/api/mission")
async def api_mission(request: MissionRequest) -> Any:
    compile_func = _resolve_nlpmc_compiler()
    if compile_func is None:
        return _nlpmc_not_available_response()

    try:
        try:
            result = compile_func(human_intent_str=request.human_intent_str)
        except TypeError:
            result = compile_func(request.human_intent_str)

        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "error": str(exc) if str(exc) else exc.__class__.__name__,
            },
        )

    mission_id = None
    staged_path = STAGED_PATH
    if isinstance(result, dict):
        mission_id = result.get("mission_id")
        staged_path = result.get("staged_path", STAGED_PATH)
    elif isinstance(result, str):
        mission_id = result

    if not mission_id:
        mission_id = f"sha256:{hashlib.sha256(request.human_intent_str.encode('utf-8')).hexdigest()}"

    return {"ok": True, "mission_id": mission_id, "staged_path": staged_path}


@app.post("/api/chat")
async def api_chat(request: ChatRequest) -> Any:
    decision = decide_chat_route_v2(request.message)
    if decision.kind == "DIRECT_ANSWER":
        return {
            "ok": True,
            "kind": "DIRECT_ANSWER",
            "assistant_message": decision.answer_text or "",
            "confidence": decision.confidence,
        }

    compile_func = _resolve_nlpmc_compiler()
    if compile_func is None:
        return _nlpmc_not_available_response()

    try:
        try:
            result = compile_func(human_intent_str=request.message)
        except TypeError:
            result = compile_func(request.message)

        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "error": str(exc) if str(exc) else exc.__class__.__name__,
                "kind": "MISSION",
            },
        )

    mission_staged_path = STAGED_PATH
    mission_request_preview: Dict[str, Any] = {}
    if isinstance(result, dict):
        mission_staged_path = str(result.get("staged_path", STAGED_PATH))
        payload = result.get("payload")
        if isinstance(payload, dict):
            mission_request_preview = payload

    return {
        "ok": True,
        "kind": "MISSION",
        "assistant_message": "Queued. Streaming progress and verified artifacts as they arrive.",
        "mission_staged_path": mission_staged_path,
        "mission_request_preview": mission_request_preview,
    }


def main() -> None:
    import uvicorn

    uvicorn.run("tools.mission_control.stream_server_v1:app", host="127.0.0.1", port=7890)


if __name__ == "__main__":
    main()
