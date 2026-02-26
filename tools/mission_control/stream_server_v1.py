from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import json
import os
import time
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from tools.mission_control._signal_parse_v1 import map_trace_class, parse_signal_line
from tools.mission_control._state_discovery_v1 import build_current_state_payload


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGED_PATH = ".omega_cache/mission_staging/pending_mission.json"


app = FastAPI(title="Mission Control Stream Server v1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class MissionRequest(BaseModel):
    human_intent_str: str


def _now_unix_ms() -> int:
    return int(time.time() * 1000)


def _select_log_path(repo_root: Path = REPO_ROOT) -> Optional[Path]:
    candidates = []

    env_path = os.getenv("MC_RUNAWAY_LOG_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())

    candidates.append(repo_root / "runaway_evolution.log")
    candidates.append(repo_root / "runs" / "runaway_evolution.log")

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


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
            selected_path = _select_log_path()
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


def main() -> None:
    import uvicorn

    uvicorn.run("tools.mission_control.stream_server_v1:app", host="127.0.0.1", port=7890)


if __name__ == "__main__":
    main()
