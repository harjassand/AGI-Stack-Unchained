"""Backend interface for LLM proposer generation (root overlay)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from orchestrator.llm_backend_replay import ReplayBackend
from orchestrator.llm_call_log import LLMCallLogger
from orchestrator.llm_cache import PromptCache
from orchestrator.llm_limits import LLMBackendLimits, LimitEnforcingBackend

_MLX_MODEL_CACHE: dict[tuple[str, str, str, bool], tuple[Any, Any]] = {}
_MLX_MUTATOR_SYSTEM_PROMPT = "You are a deterministic code mutator. Output a single JSON object only. No markdown."
_U64_MOD = 1 << 64


class LLMBackend(Protocol):
    def generate(self, prompt: str) -> str:
        raise NotImplementedError


@dataclass
class MockBackend:
    response: str
    mode: str = "static"
    calls: int = 0
    cache: PromptCache | None = None
    logger: LLMCallLogger | None = None

    def generate(self, prompt: str) -> str:
        cache_hit = False
        if self.cache:
            cached = self.cache.get(prompt)
            if cached is not None:
                cache_hit = True
                response = cached
                if self.logger:
                    self.logger.record(prompt=prompt, response=response, cache_hit=True)
                return response
        self.calls += 1
        if self.mode == "invalid_then_valid" and self.calls == 1:
            response = "{"
        else:
            response = self.response
        if self.cache:
            self.cache.set(prompt, response)
        if self.logger:
            self.logger.record(prompt=prompt, response=response, cache_hit=cache_hit)
        return response


def _sha256_prefixed(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso_utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_openai_model(model: str) -> str:
    value = str(model or "").strip()
    if not value:
        raise ValueError("ORCH_OPENAI_MODEL must be set")
    if not value.startswith(("gpt-", "o1", "o3", "o4")):
        raise ValueError("ORCH_OPENAI_MODEL must be a Responses-compatible model id")
    return value


def _validate_anthropic_model(model: str) -> str:
    value = str(model or "").strip()
    if not value:
        raise ValueError("ORCH_ANTHROPIC_MODEL must be set")
    if not value.startswith("claude-"):
        raise ValueError("ORCH_ANTHROPIC_MODEL must start with claude-")
    return value


def _gemini_removed() -> ValueError:
    return ValueError("Gemini backend removed — use ORCH_LLM_BACKEND=mlx")


def _http_post_json(*, url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=False).encode("utf-8")
    max_attempts = int(os.environ.get("ORCH_LLM_RETRY_429_MAX_ATTEMPTS", "6") or 6)
    delay_s = float(os.environ.get("ORCH_LLM_RETRY_429_BASE_DELAY_S", "1.0") or 1.0)
    delay_s = max(0.1, delay_s)
    for attempt in range(max(1, max_attempts)):
        req = Request(url=url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        for key, value in headers.items():
            req.add_header(str(key), str(value))
        try:
            with urlopen(req, timeout=60) as resp:  # nosec: B310
                raw = resp.read().decode("utf-8")
            break
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt + 1 < max_attempts:
                time.sleep(delay_s)
                delay_s = min(30.0, delay_s * 2.0)
                continue
            raise ValueError(f"live llm request failed: HTTP {exc.code}: {detail[:240]}") from exc
        except URLError as exc:
            raise ValueError(f"live llm request failed: {exc}") from exc
    try:
        payload_obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("live llm request returned non-JSON payload") from exc
    if not isinstance(payload_obj, dict):
        raise ValueError("live llm request returned non-object payload")
    return payload_obj


def _extract_openai_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text
    outputs = payload.get("output")
    texts: list[str] = []
    if isinstance(outputs, list):
        for item in outputs:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if str(block.get("type", "")).strip() not in {"output_text", "text"}:
                    continue
                for key in ("text", "value"):
                    value = block.get(key)
                    if isinstance(value, str) and value:
                        texts.append(value)
                        break
    response = "".join(texts).strip()
    if not response:
        raise ValueError("openai response contained no assistant text")
    return response


def _extract_anthropic_text(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        raise ValueError("anthropic response missing content list")
    texts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if str(block.get("type", "")).strip() != "text":
            continue
        text = block.get("text")
        if isinstance(text, str) and text:
            texts.append(text)
    response = "".join(texts).strip()
    if not response:
        raise ValueError("anthropic response contained no assistant text")
    return response


def _append_replay_row(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")


def _load_replay_entries(path: Path, *, provider: str, model: str) -> dict[tuple[str, str, str], str]:
    if not path.exists():
        raise FileNotFoundError(f"replay file not found: {path}")
    entries: dict[tuple[str, str, str], str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError("replay line must be a JSON object")
        if str(payload.get("schema_version", "")).strip() != "orch_llm_replay_row_v1":
            continue
        row_provider = str(payload.get("backend", "")).strip()
        row_model = str(payload.get("model", "")).strip()
        if row_provider != provider or row_model != model:
            continue
        prompt = payload.get("prompt")
        response = payload.get("response")
        prompt_sha = payload.get("prompt_sha256")
        response_sha = payload.get("response_sha256")
        if not isinstance(prompt, str) or not isinstance(response, str):
            raise ValueError("replay rows must include prompt and response")
        if not isinstance(prompt_sha, str) or not isinstance(response_sha, str):
            raise ValueError("replay rows must include prompt_sha256 and response_sha256")
        if prompt_sha != _sha256_prefixed(prompt):
            raise ValueError("replay row prompt_sha256 mismatch")
        if response_sha != _sha256_prefixed(response):
            raise ValueError("replay row response_sha256 mismatch")
        key = (row_provider, row_model, prompt_sha)
        entries[key] = response
    if not entries:
        raise ValueError("replay file contains no matching provider/model entries")
    return entries


def _normalize_u64(value: int) -> int:
    return int(value) % _U64_MOD


def _read_seed_u64() -> int:
    for key in ("ORCH_LLM_SEED_U64", "OMEGA_RUN_SEED_U64"):
        raw = str(os.environ.get(key, "")).strip()
        if not raw:
            continue
        try:
            return _normalize_u64(int(raw))
        except Exception:  # noqa: BLE001
            continue
    return 0


def _derive_call_seed_u64(*, base_seed_u64: int, call_index_u64: int) -> int:
    payload = {
        "schema_id": "orch_llm_call_seed_v1",
        "base_seed_u64": int(_normalize_u64(base_seed_u64)),
        "call_index_u64": int(_normalize_u64(call_index_u64)),
    }
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(canon).digest()
    return int.from_bytes(digest[-8:], "big", signed=False)


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _coerce_temperature(value: str | None, *, default: float) -> float:
    try:
        out = float(str(value or "").strip())
    except Exception:  # noqa: BLE001
        out = float(default)
    return max(0.0, min(2.0, float(out)))


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


def _load_mlx_modules() -> tuple[Any, Any, Any, Any]:
    try:
        import mlx.core as mx
        from mlx_lm.generate import generate as mlx_generate
        from mlx_lm.sample_utils import make_sampler
        from mlx_lm.utils import load as mlx_load
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"mlx backend unavailable: {exc}") from exc
    return mx, mlx_load, mlx_generate, make_sampler


def _load_mlx_model_and_tokenizer(
    *,
    model_id: str,
    revision: str,
    adapter_path: str,
    trust_remote_code: bool,
) -> tuple[Any, Any]:
    key = (str(model_id), str(revision), str(adapter_path), bool(trust_remote_code))
    cached = _MLX_MODEL_CACHE.get(key)
    if cached is not None:
        return cached

    _, mlx_load, _, _ = _load_mlx_modules()
    load_kwargs: dict[str, Any] = {"lazy": False}
    if revision:
        load_kwargs["revision"] = revision
    if adapter_path:
        load_kwargs["adapter_path"] = adapter_path

    model, tokenizer = mlx_load(model_id, **load_kwargs)
    _MLX_MODEL_CACHE[key] = (model, tokenizer)
    return model, tokenizer


def _format_mlx_prompt(*, tokenizer: Any, prompt: str) -> str:
    apply_chat_template = getattr(tokenizer, "apply_chat_template", None)
    if callable(apply_chat_template):
        messages = [
            {"role": "system", "content": _MLX_MUTATOR_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        try:
            rendered = apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            if isinstance(rendered, str) and rendered.strip():
                return rendered
        except Exception:  # noqa: BLE001
            pass
    return prompt


def _build_mlx_sampler(*, make_sampler: Any, temperature_f64: float, top_p_f64: float) -> Any:
    # temp<=0 implies greedy behavior; mutators force this via env to reduce nondeterminism.
    greedy = float(temperature_f64) <= 0.0
    temp = 0.0 if greedy else float(temperature_f64)
    top_p = 1.0 if greedy else float(top_p_f64)
    try:
        return make_sampler(
            temp=temp,
            top_p=top_p,
            min_p=0.0,
            min_tokens_to_keep=1,
            top_k=1 if greedy else 0,
            xtc_probability=0.0,
            xtc_threshold=0.0,
            xtc_special_tokens=[],
        )
    except TypeError:
        return make_sampler(temp=temp, top_p=top_p)


@dataclass
class ProviderReplayBackend:
    provider: str
    model: str
    entries: dict[tuple[str, str, str], str]
    cache: PromptCache | None = None
    logger: LLMCallLogger | None = None
    calls: int = 0

    @classmethod
    def from_path(
        cls,
        *,
        provider: str,
        model: str,
        replay_path: str | Path,
        cache: PromptCache | None = None,
        logger: LLMCallLogger | None = None,
    ) -> "ProviderReplayBackend":
        normalized_provider = str(provider).strip().lower()
        if normalized_provider == "openai":
            normalized_model = _validate_openai_model(model)
        elif normalized_provider == "anthropic":
            normalized_model = _validate_anthropic_model(model)
        elif normalized_provider == "gemini":
            raise _gemini_removed()
        else:
            raise ValueError(f"unsupported provider: {provider}")
        replay_entries = _load_replay_entries(Path(replay_path), provider=normalized_provider, model=normalized_model)
        return cls(
            provider=normalized_provider,
            model=normalized_model,
            entries=replay_entries,
            cache=cache,
            logger=logger,
        )

    def generate(self, prompt: str) -> str:
        cache_hit = False
        if self.cache:
            cached = self.cache.get(prompt)
            if cached is not None:
                cache_hit = True
                response = cached
                if self.logger:
                    self.logger.record(prompt=prompt, response=response, cache_hit=True)
                return response

        prompt_sha = _sha256_prefixed(prompt)
        key = (self.provider, self.model, prompt_sha)
        response = self.entries.get(key)
        if response is None:
            raise ValueError("replay backend missing prompt")
        self.calls += 1
        if self.cache:
            self.cache.set(prompt, response)
        if self.logger:
            self.logger.record(prompt=prompt, response=response, cache_hit=cache_hit)
        return response


@dataclass
class ProviderHarvestBackend:
    provider: str
    model: str
    replay_path: Path
    api_key: str
    anthropic_version: str = "2023-06-01"
    cache: PromptCache | None = None
    logger: LLMCallLogger | None = None
    calls: int = 0

    def _request_openai(self, prompt: str) -> tuple[str, dict[str, Any]]:
        payload = _http_post_json(
            url="https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self.api_key}"},
            payload={"model": self.model, "input": prompt},
        )
        return _extract_openai_text(payload), payload

    def _request_anthropic(self, prompt: str) -> tuple[str, dict[str, Any]]:
        payload = _http_post_json(
            url="https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self.anthropic_version,
            },
            payload={
                "model": self.model,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        return _extract_anthropic_text(payload), payload

    def _request_live(self, prompt: str) -> tuple[str, dict[str, Any]]:
        if self.provider == "openai":
            return self._request_openai(prompt)
        if self.provider == "anthropic":
            return self._request_anthropic(prompt)
        if self.provider == "gemini":
            raise _gemini_removed()
        raise ValueError(f"unsupported provider: {self.provider}")

    def generate(self, prompt: str) -> str:
        cache_hit = False
        if self.cache:
            cached = self.cache.get(prompt)
            if cached is not None:
                cache_hit = True
                response = cached
                if self.logger:
                    self.logger.record(prompt=prompt, response=response, cache_hit=True)
                return response

        if os.environ.get("ORCH_LLM_LIVE_OK", "") != "1":
            raise ValueError("ORCH_LLM_LIVE_OK=1 is required for harvest backends")
        response, raw_payload = self._request_live(prompt)
        self.calls += 1

        row = {
            "schema_version": "orch_llm_replay_row_v1",
            "backend": self.provider,
            "model": self.model,
            "prompt_sha256": _sha256_prefixed(prompt),
            "response_sha256": _sha256_prefixed(response),
            "prompt": prompt,
            "response": response,
            "created_at_utc": _iso_utc_now(),
            "raw_response_json": raw_payload,
        }
        _append_replay_row(self.replay_path, row)
        if self.cache:
            self.cache.set(prompt, response)
        if self.logger:
            self.logger.record(prompt=prompt, response=response, cache_hit=cache_hit)
        return response


@dataclass
class MlxBackend:
    model_id: str
    revision: str
    adapter_path: str
    trust_remote_code: bool
    temperature_f64: float
    top_p_f64: float
    max_tokens_u64: int
    base_seed_u64: int
    replay_path: Path | None
    cache: PromptCache | None = None
    logger: LLMCallLogger | None = None
    calls: int = 0
    call_index_u64: int = 0

    def generate(self, prompt: str) -> str:
        cache_hit = False
        if self.cache:
            cached = self.cache.get(prompt)
            if cached is not None:
                cache_hit = True
                if self.logger:
                    self.logger.record(prompt=prompt, response=cached, cache_hit=True)
                return cached

        mx, _, mlx_generate, make_sampler = _load_mlx_modules()
        model, tokenizer = _load_mlx_model_and_tokenizer(
            model_id=self.model_id,
            revision=self.revision,
            adapter_path=self.adapter_path,
            trust_remote_code=self.trust_remote_code,
        )
        prompt_text = _format_mlx_prompt(tokenizer=tokenizer, prompt=prompt)
        call_seed_u64 = _derive_call_seed_u64(
            base_seed_u64=int(self.base_seed_u64),
            call_index_u64=int(self.call_index_u64),
        )
        mx.random.seed(int(call_seed_u64))
        sampler = _build_mlx_sampler(
            make_sampler=make_sampler,
            temperature_f64=float(self.temperature_f64),
            top_p_f64=float(self.top_p_f64),
        )
        response = mlx_generate(
            model,
            tokenizer,
            prompt_text,
            max_tokens=int(self.max_tokens_u64),
            sampler=sampler,
            verbose=False,
        )
        if not isinstance(response, str):
            response = str(response)
        self.calls += 1
        self.call_index_u64 += 1

        if self.replay_path is not None:
            row = {
                "schema_version": "orch_llm_replay_row_v1",
                "backend": "mlx",
                "model": self.model_id,
                "revision": self.revision,
                "adapter_path": self.adapter_path,
                "trust_remote_code_b": bool(self.trust_remote_code),
                "prompt_sha256": _sha256_prefixed(prompt),
                "response_sha256": _sha256_prefixed(response),
                "prompt": prompt,
                "response": response,
                "created_at_utc": _iso_utc_now(),
                "generation_knobs": {
                    "temperature_f64": float(self.temperature_f64),
                    "top_p_f64": float(self.top_p_f64),
                    "max_tokens_u64": int(self.max_tokens_u64),
                    "base_seed_u64": int(self.base_seed_u64),
                    "call_index_u64": int(self.call_index_u64 - 1),
                    "call_seed_u64": int(call_seed_u64),
                    "greedy_b": bool(float(self.temperature_f64) <= 0.0),
                },
            }
            _append_replay_row(self.replay_path, row)

        if self.cache:
            self.cache.set(prompt, response)
        if self.logger:
            self.logger.record(prompt=prompt, response=response, cache_hit=cache_hit)
        return response


def get_backend(logger: LLMCallLogger | None = None) -> LLMBackend:
    backend_raw = str(os.environ.get("ORCH_LLM_BACKEND", "mock")).strip()
    backend = backend_raw.lower() or "mock"
    if backend in {"gemini", "google", "gemini_replay", "gemini_harvest"}:
        raise _gemini_removed()

    cache_dir = os.environ.get("ORCH_LLM_CACHE_DIR")
    cache = PromptCache(Path(cache_dir)) if cache_dir else None
    limits = LLMBackendLimits.from_env()

    if backend == "mock":
        response = os.environ.get("ORCH_LLM_MOCK_RESPONSE") or "{}"
        mode = os.environ.get("ORCH_LLM_MOCK_MODE", "static").lower()
        return LimitEnforcingBackend(
            backend=MockBackend(response=response, mode=mode, cache=cache, logger=logger),
            limits=limits,
        )
    if backend == "replay":
        path = os.environ.get("ORCH_LLM_REPLAY_PATH")
        if not path:
            raise ValueError("ORCH_LLM_REPLAY_PATH is required for replay backend")
        return LimitEnforcingBackend(
            backend=ReplayBackend.from_path(path, cache=cache, logger=logger),
            limits=limits,
        )
    if backend == "openai_replay":
        replay_path = os.environ.get("ORCH_LLM_REPLAY_PATH")
        if not replay_path:
            raise ValueError("ORCH_LLM_REPLAY_PATH is required for openai_replay backend")
        model = _validate_openai_model(os.environ.get("ORCH_OPENAI_MODEL", "gpt-4.1"))
        return LimitEnforcingBackend(
            backend=ProviderReplayBackend.from_path(
                provider="openai",
                model=model,
                replay_path=replay_path,
                cache=cache,
                logger=logger,
            ),
            limits=limits,
        )
    if backend == "anthropic_replay":
        replay_path = os.environ.get("ORCH_LLM_REPLAY_PATH")
        if not replay_path:
            raise ValueError("ORCH_LLM_REPLAY_PATH is required for anthropic_replay backend")
        model = _validate_anthropic_model(os.environ.get("ORCH_ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"))
        return LimitEnforcingBackend(
            backend=ProviderReplayBackend.from_path(
                provider="anthropic",
                model=model,
                replay_path=replay_path,
                cache=cache,
                logger=logger,
            ),
            limits=limits,
        )
    if backend == "openai_harvest":
        replay_path = os.environ.get("ORCH_LLM_REPLAY_PATH")
        if not replay_path:
            raise ValueError("ORCH_LLM_REPLAY_PATH is required for openai_harvest backend")
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for openai_harvest backend")
        model = _validate_openai_model(os.environ.get("ORCH_OPENAI_MODEL", "gpt-4.1"))
        return LimitEnforcingBackend(
            backend=ProviderHarvestBackend(
                provider="openai",
                model=model,
                replay_path=Path(replay_path),
                api_key=api_key,
                cache=cache,
                logger=logger,
            ),
            limits=limits,
        )
    if backend == "anthropic_harvest":
        replay_path = os.environ.get("ORCH_LLM_REPLAY_PATH")
        if not replay_path:
            raise ValueError("ORCH_LLM_REPLAY_PATH is required for anthropic_harvest backend")
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for anthropic_harvest backend")
        model = _validate_anthropic_model(os.environ.get("ORCH_ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"))
        anthropic_version = str(os.environ.get("ORCH_ANTHROPIC_VERSION", "2023-06-01")).strip() or "2023-06-01"
        return LimitEnforcingBackend(
            backend=ProviderHarvestBackend(
                provider="anthropic",
                model=model,
                replay_path=Path(replay_path),
                api_key=api_key,
                anthropic_version=anthropic_version,
                cache=cache,
                logger=logger,
            ),
            limits=limits,
        )
    if backend == "mlx":
        replay_path_raw = str(os.environ.get("ORCH_LLM_REPLAY_PATH", "")).strip()
        replay_path = Path(replay_path_raw).expanduser().resolve() if replay_path_raw else None
        return LimitEnforcingBackend(
            backend=MlxBackend(
                model_id=str(
                    os.environ.get(
                        "ORCH_MLX_MODEL",
                        "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit",
                    )
                ).strip()
                or "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit",
                revision=str(os.environ.get("ORCH_MLX_REVISION", "")).strip(),
                adapter_path=str(os.environ.get("ORCH_MLX_ADAPTER_PATH", "")).strip(),
                trust_remote_code=bool(_truthy(os.environ.get("ORCH_MLX_TRUST_REMOTE_CODE"))),
                temperature_f64=_coerce_temperature(os.environ.get("ORCH_LLM_TEMPERATURE"), default=0.2),
                top_p_f64=_coerce_top_p(os.environ.get("ORCH_LLM_TOP_P"), default=0.95),
                max_tokens_u64=_coerce_positive_int(os.environ.get("ORCH_LLM_MAX_TOKENS"), default=4096),
                base_seed_u64=_read_seed_u64(),
                replay_path=replay_path,
                cache=cache,
                logger=logger,
            ),
            limits=limits,
        )
    raise ValueError(f"unknown llm backend: {backend}")
