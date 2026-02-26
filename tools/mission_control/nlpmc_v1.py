"""NLPMC v1 mission compiler and atomic staging writer."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_SCHEMA_REL = Path("Genesis/schema/v19_0/mission_request_v1.jsonschema")
_CAPREG_REL = Path("campaigns/rsi_omega_daemon_v19_0_super_unified/omega_capability_registry_v2.json")
_PROMPT_HEADER = "You are an RE4 deterministic translation router… Output GCJ-1 compatible JSON only."
_DEFAULT_STAGING_RELPATH = ".omega_cache/mission_staging/pending_mission.json"
_RETRY_TEMPERATURES = (0.0, 0.2, 0.4)


def compile_and_stage_mission(
    human_intent_str: str,
    *,
    repo_root: str = ".",
    max_retries: int = 3,
    staging_relpath: str = _DEFAULT_STAGING_RELPATH,
) -> dict:
    """
    Returns:
      {
        "mission_id": "sha256:...",
        "payload": <mission_request_v1 dict>,
        "staged_path": <string path written>
      }
    Raises:
      RuntimeError with stable error codes in message prefix.
    """

    repo_root_path = Path(repo_root).resolve()
    schema_path = repo_root_path / _SCHEMA_REL
    capreg_path = repo_root_path / _CAPREG_REL

    schema = _load_required_json(path=schema_path, error_code="NLPMC_SCHEMA_NOT_FOUND")
    capreg = _load_required_json(path=capreg_path, error_code="NLPMC_CAPREG_NOT_FOUND")
    system_prompt = _build_system_prompt(schema=schema, capreg=capreg)

    human_intent = str(human_intent_str)
    user_prompt = human_intent.strip()
    if not user_prompt:
        raise RuntimeError("NLPMC_EMPTY_INTENT: human_intent_str must be non-empty")

    retries = max(1, int(max_retries))
    attempt_temps = [_RETRY_TEMPERATURES[min(i, len(_RETRY_TEMPERATURES) - 1)] for i in range(retries)]

    last_err = "unknown"
    for attempt_index, temperature_f64 in enumerate(attempt_temps):
        backend = _make_backend(temperature_f64=temperature_f64, attempt_index=attempt_index)
        try:
            raw = backend.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception as exc:  # noqa: BLE001
            last_err = f"GENERATION_FAILED:{exc}"
            continue
        finally:
            backend.close()

        try:
            raw_payload = _strict_json_object(raw)
            payload = _build_schema_skeleton(schema=schema)
            _merge_allowed_schema_keys(payload=payload, candidate=raw_payload, schema=schema)
            _enforce_schema_consts(payload=payload, schema=schema)
            _enforce_human_intent_echo_if_requested(payload=payload, schema=schema, human_intent_str=human_intent)
            _ensure_anyof_selector(payload=payload)

            no_id = dict(payload)
            no_id.pop("mission_id", None)
            mission_id = _sha256_prefixed(_canon_bytes(no_id, repo_root=repo_root_path))

            payload_with_id = dict(payload)
            payload_with_id["mission_id"] = mission_id
            payload_for_validation = payload_with_id if _schema_allows_field(schema=schema, field="mission_id") else payload

            _validate_with_cdel(payload=payload_for_validation, repo_root=repo_root_path)
            payload_to_stage = payload_for_validation
            staged_path = _atomic_stage_write(
                repo_root=repo_root_path,
                staging_relpath=staging_relpath,
                payload=payload_to_stage,
            )
            return {
                "mission_id": mission_id,
                "payload": payload_to_stage,
                "staged_path": staged_path,
            }
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)

    raise RuntimeError(f"NLPMC_VALIDATION_FAILED: {last_err}")


def _build_system_prompt(*, schema: dict[str, Any], capreg: dict[str, Any]) -> str:
    schema_min = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    capreg_min = json.dumps(capreg, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "\n".join((_PROMPT_HEADER, schema_min, capreg_min))


def _load_required_json(*, path: Path, error_code: str) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"{error_code}: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"{error_code}: invalid json at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{error_code}: expected object json at {path}")
    return payload


def _strict_json_object(raw: str) -> dict[str, Any]:
    src = str(raw).strip()
    if not src:
        raise RuntimeError("NLPMC_JSON_PARSE_FAILED: empty response")

    parse_errors: list[str] = []
    for candidate in _json_parse_candidates(src):
        decoder = json.JSONDecoder()
        try:
            value, end_index = decoder.raw_decode(candidate)
        except Exception as exc:  # noqa: BLE001
            parse_errors.append(str(exc))
            continue
        if end_index != len(candidate):
            parse_errors.append("trailing text present")
            continue
        if not isinstance(value, dict):
            parse_errors.append("response must be a json object")
            continue
        return value

    tail_error = parse_errors[-1] if parse_errors else "unable to decode model output"
    raise RuntimeError(f"NLPMC_JSON_PARSE_FAILED: {tail_error}")


def _json_parse_candidates(src: str) -> list[str]:
    candidates: list[str] = [src]

    stripped_fence = _strip_code_fence(src)
    if stripped_fence:
        candidates.append(stripped_fence)

    extracted_object = _extract_first_json_object(src)
    if extracted_object:
        candidates.append(extracted_object)

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        trimmed = candidate.strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        unique.append(trimmed)
    return unique


def _strip_code_fence(src: str) -> str | None:
    if not src.startswith("```"):
        return None
    lines = src.splitlines()
    if len(lines) < 3:
        return None
    if lines[-1].strip() != "```":
        return None
    body = "\n".join(lines[1:-1]).strip()
    return body or None


def _extract_first_json_object(src: str) -> str | None:
    start_index: int | None = None
    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(src):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            if depth == 0:
                start_index = index
            depth += 1
            continue

        if char == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start_index is not None:
                return src[start_index : index + 1]

    return None


def _enforce_schema_consts(*, payload: dict[str, Any], schema: dict[str, Any]) -> None:
    props = schema.get("properties")
    if not isinstance(props, dict):
        return
    for key in ("schema_name", "schema_version"):
        row = props.get(key)
        if not isinstance(row, dict):
            continue
        required_const = row.get("const")
        if required_const is not None:
            payload[key] = required_const


def _enforce_human_intent_echo_if_requested(*, payload: dict[str, Any], schema: dict[str, Any], human_intent_str: str) -> None:
    props = schema.get("properties")
    if isinstance(props, dict) and "human_intent_str" in props:
        payload["human_intent_str"] = human_intent_str


def _build_schema_skeleton(*, schema: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    props = schema.get("properties")
    if not isinstance(props, dict):
        return payload

    for key, row in props.items():
        if isinstance(row, dict) and "const" in row:
            payload[key] = row["const"]
    return payload


def _merge_allowed_schema_keys(*, payload: dict[str, Any], candidate: dict[str, Any], schema: dict[str, Any]) -> None:
    props = schema.get("properties")
    allowed_keys = set(props.keys()) if isinstance(props, dict) else set()
    for key, value in candidate.items():
        if key in allowed_keys:
            payload[key] = value


def _ensure_anyof_selector(*, payload: dict[str, Any]) -> None:
    objective_tags = payload.get("objective_tags")
    if objective_tags is not None and not isinstance(objective_tags, list):
        payload.pop("objective_tags", None)

    allowed_caps = payload.get("allowed_capability_ids")
    if allowed_caps is not None and not isinstance(allowed_caps, list):
        payload.pop("allowed_capability_ids", None)

    domain = payload.get("domain")
    if domain is not None:
        if isinstance(domain, str) and domain.strip():
            payload["domain"] = domain.strip()
        else:
            payload.pop("domain", None)

    has_objective_tags = "objective_tags" in payload
    has_domain = "domain" in payload
    has_allowed_caps = "allowed_capability_ids" in payload
    if not has_objective_tags and not has_domain and not has_allowed_caps:
        payload["domain"] = "general"


def _schema_allows_field(*, schema: dict[str, Any], field: str) -> bool:
    props = schema.get("properties")
    if not isinstance(props, dict):
        return True
    if field in props:
        return True
    additional = schema.get("additionalProperties")
    if isinstance(additional, bool):
        return additional
    return True


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _ensure_cdel_path(repo_root: Path) -> None:
    cdel_root = (repo_root / "CDEL-v2").resolve()
    cdel_root_str = str(cdel_root)
    if cdel_root_str not in sys.path:
        sys.path.insert(0, cdel_root_str)


def _canon_bytes(payload: dict[str, Any], *, repo_root: Path) -> bytes:
    _ensure_cdel_path(repo_root)
    from cdel.v1_7r.canon import canon_bytes

    return canon_bytes(payload)


def _validate_with_cdel(*, payload: dict[str, Any], repo_root: Path) -> None:
    _ensure_cdel_path(repo_root)
    from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

    with _temporary_env("OMEGA_REPO_ROOT", str(repo_root)):
        validate_schema_v19(payload, "mission_request_v1")


@contextmanager
def _temporary_env(key: str, value: str):
    prev = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev


def _atomic_stage_write(*, repo_root: Path, staging_relpath: str, payload: dict[str, Any]) -> str:
    staging_arg = Path(staging_relpath)
    staging_path = staging_arg if staging_arg.is_absolute() else (repo_root / staging_arg)
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    if staging_path.suffix:
        tmp_path = staging_path.with_suffix(f"{staging_path.suffix}.tmp.{os.getpid()}")
    else:
        tmp_path = Path(f"{staging_path}.tmp.{os.getpid()}")

    body = _canon_bytes(payload, repo_root=repo_root)
    try:
        with tmp_path.open("wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, staging_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    dir_fd = os.open(staging_path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)

    return str(staging_arg if not staging_arg.is_absolute() else staging_path)


class _NlpmcMlxBackend:
    def __init__(self, *, temperature_f64: float, attempt_index: int) -> None:
        backend_name = str(os.environ.get("ORCH_LLM_BACKEND", "mlx")).strip().lower() or "mlx"
        if backend_name != "mlx":
            raise RuntimeError("NLPMC_NOT_AVAILABLE: ORCH_LLM_BACKEND must be mlx")

        self.temperature_f64 = float(temperature_f64)
        self.attempt_index = int(max(0, attempt_index))
        self.model_id = str(
            os.environ.get(
                "ORCH_MLX_MODEL",
                "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit",
            )
        ).strip() or "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit"
        self.revision = str(os.environ.get("ORCH_MLX_REVISION", "")).strip()
        self.adapter_path = str(os.environ.get("ORCH_MLX_ADAPTER_PATH", "")).strip()
        self.max_tokens_u64 = _coerce_positive_int(os.environ.get("ORCH_LLM_MAX_TOKENS"), default=4096)
        self.top_p_f64 = _coerce_top_p(os.environ.get("ORCH_LLM_TOP_P"), default=0.95)
        self.trust_remote_code = _truthy(os.environ.get("ORCH_MLX_TRUST_REMOTE_CODE"))
        self.base_seed_u64 = _read_seed_u64()

        self._orch_llm = None
        self._mx = None
        self._model = None
        self._tokenizer = None
        self._mlx_generate = None
        self._make_sampler = None

    def _load_runtime(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        import orchestrator.llm_backend as orch_llm

        mx, mlx_load, mlx_generate, make_sampler = orch_llm._load_mlx_modules()
        load_kwargs: dict[str, Any] = {"lazy": False}
        if self.revision:
            load_kwargs["revision"] = self.revision
        if self.adapter_path:
            load_kwargs["adapter_path"] = self.adapter_path
        model, tokenizer = mlx_load(self.model_id, **load_kwargs)

        self._orch_llm = orch_llm
        self._mx = mx
        self._model = model
        self._tokenizer = tokenizer
        self._mlx_generate = mlx_generate
        self._make_sampler = make_sampler

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> str:
        self._load_runtime()
        assert self._orch_llm is not None
        assert self._mx is not None
        assert self._model is not None
        assert self._tokenizer is not None
        assert self._mlx_generate is not None
        assert self._make_sampler is not None

        prompt_text = _render_prompt(
            tokenizer=self._tokenizer,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        call_seed_u64 = self._orch_llm._derive_call_seed_u64(
            base_seed_u64=int(self.base_seed_u64),
            call_index_u64=int(self.attempt_index),
        )
        self._mx.random.seed(int(call_seed_u64))
        sampler = self._orch_llm._build_mlx_sampler(
            make_sampler=self._make_sampler,
            temperature_f64=float(self.temperature_f64),
            top_p_f64=float(self.top_p_f64),
        )
        response = self._mlx_generate(
            self._model,
            self._tokenizer,
            prompt_text,
            max_tokens=int(self.max_tokens_u64),
            sampler=sampler,
            verbose=False,
        )
        return response if isinstance(response, str) else str(response)

    def close(self) -> None:
        model = self._model
        tokenizer = self._tokenizer
        self._model = None
        self._tokenizer = None
        self._mlx_generate = None
        self._make_sampler = None

        if self._orch_llm is not None:
            try:
                cache = getattr(self._orch_llm, "_MLX_MODEL_CACHE", None)
                if isinstance(cache, dict):
                    cache.clear()
            except Exception:  # noqa: BLE001
                pass

        if model is not None:
            del model
        if tokenizer is not None:
            del tokenizer

        try:
            if self._mx is None:
                import mlx.core as mx
            else:
                mx = self._mx
            mx.metal.clear_cache()
        except Exception:  # noqa: BLE001
            pass

        self._mx = None
        self._orch_llm = None


def _render_prompt(*, tokenizer: Any, system_prompt: str, user_prompt: str) -> str:
    apply_chat_template = getattr(tokenizer, "apply_chat_template", None)
    if callable(apply_chat_template):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            rendered = apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            if isinstance(rendered, str) and rendered.strip():
                return rendered
        except Exception:  # noqa: BLE001
            pass
    return f"{system_prompt}\n{user_prompt}"


def _make_backend(*, temperature_f64: float, attempt_index: int) -> _NlpmcMlxBackend:
    return _NlpmcMlxBackend(temperature_f64=temperature_f64, attempt_index=attempt_index)


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _coerce_top_p(value: str | None, *, default: float) -> float:
    try:
        out = float(str(value or "").strip())
    except Exception:  # noqa: BLE001
        out = float(default)
    return max(0.0, min(1.0, float(out)))


def _coerce_positive_int(value: str | None, *, default: int) -> int:
    try:
        out = int(str(value or "").strip())
    except Exception:  # noqa: BLE001
        out = int(default)
    return max(1, int(out))


def _read_seed_u64() -> int:
    for key in ("ORCH_LLM_SEED_U64", "OMEGA_RUN_SEED_U64"):
        raw = str(os.environ.get(key, "")).strip()
        if not raw:
            continue
        try:
            return int(raw) % (1 << 64)
        except Exception:  # noqa: BLE001
            continue
    return 0
