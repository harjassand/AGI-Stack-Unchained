"""CSI metering utilities for v2.2."""

from __future__ import annotations

import ast
import json
import re
import hashlib
from types import TracebackType
from typing import Any, Callable


class CSIMeter:
    """Context manager that counts deterministic operations for CSI."""

    def __init__(self) -> None:
        self.counts = {
            "sha256_calls_total": 0,
            "sha256_bytes_total": 0,
            "json_dumps_calls_total": 0,
            "json_dumps_bytes_total": 0,
            "json_loads_calls_total": 0,
            "json_loads_bytes_total": 0,
            "ast_parse_calls_total": 0,
            "regex_compile_calls_total": 0,
            "regex_match_calls_total": 0,
        }
        self._orig_sha256: Callable[..., Any] | None = None
        self._orig_json_dumps: Callable[..., Any] | None = None
        self._orig_json_loads: Callable[..., Any] | None = None
        self._orig_ast_parse: Callable[..., Any] | None = None
        self._orig_re_compile: Callable[..., Any] | None = None

    def _wrap_sha256(self) -> None:
        orig = hashlib.sha256
        counts = self.counts

        class _HashWrapper:
            def __init__(self, inner: Any) -> None:
                self._inner = inner

            def update(self, data: Any = b"") -> None:
                size = _byte_len(data)
                counts["sha256_bytes_total"] += size
                self._inner.update(data)

            def digest(self) -> bytes:
                return self._inner.digest()

            def hexdigest(self) -> str:
                return self._inner.hexdigest()

            def copy(self) -> "_HashWrapper":
                return _HashWrapper(self._inner.copy())

            def __getattr__(self, name: str) -> Any:
                return getattr(self._inner, name)

        def wrapper(data: Any = b"") -> _HashWrapper:
            counts["sha256_calls_total"] += 1
            size = _byte_len(data)
            counts["sha256_bytes_total"] += size
            return _HashWrapper(orig(data))

        self._orig_sha256 = orig
        hashlib.sha256 = wrapper  # type: ignore[assignment]

    def _wrap_json(self) -> None:
        counts = self.counts
        orig_dumps = json.dumps
        orig_loads = json.loads

        def dumps_wrapper(obj: Any, *args: Any, **kwargs: Any) -> str:
            counts["json_dumps_calls_total"] += 1
            out = orig_dumps(obj, *args, **kwargs)
            counts["json_dumps_bytes_total"] += len(out.encode("utf-8"))
            return out

        def loads_wrapper(data: Any, *args: Any, **kwargs: Any) -> Any:
            counts["json_loads_calls_total"] += 1
            counts["json_loads_bytes_total"] += _byte_len(data)
            return orig_loads(data, *args, **kwargs)

        self._orig_json_dumps = orig_dumps
        self._orig_json_loads = orig_loads
        json.dumps = dumps_wrapper  # type: ignore[assignment]
        json.loads = loads_wrapper  # type: ignore[assignment]

    def _wrap_ast(self) -> None:
        counts = self.counts
        orig_parse = ast.parse

        def parse_wrapper(*args: Any, **kwargs: Any) -> Any:
            counts["ast_parse_calls_total"] += 1
            return orig_parse(*args, **kwargs)

        self._orig_ast_parse = orig_parse
        ast.parse = parse_wrapper  # type: ignore[assignment]

    def _wrap_regex(self) -> None:
        counts = self.counts
        orig_compile = re.compile

        class _PatternWrapper:
            def __init__(self, inner: re.Pattern[str]) -> None:
                self._inner = inner

            def match(self, *args: Any, **kwargs: Any) -> Any:
                counts["regex_match_calls_total"] += 1
                return self._inner.match(*args, **kwargs)

            def __getattr__(self, name: str) -> Any:
                return getattr(self._inner, name)

        def compile_wrapper(*args: Any, **kwargs: Any) -> _PatternWrapper:
            counts["regex_compile_calls_total"] += 1
            return _PatternWrapper(orig_compile(*args, **kwargs))

        self._orig_re_compile = orig_compile
        re.compile = compile_wrapper  # type: ignore[assignment]

    def __enter__(self) -> "CSIMeter":
        self._wrap_sha256()
        self._wrap_json()
        self._wrap_ast()
        self._wrap_regex()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._orig_sha256 is not None:
            hashlib.sha256 = self._orig_sha256  # type: ignore[assignment]
        if self._orig_json_dumps is not None:
            json.dumps = self._orig_json_dumps  # type: ignore[assignment]
        if self._orig_json_loads is not None:
            json.loads = self._orig_json_loads  # type: ignore[assignment]
        if self._orig_ast_parse is not None:
            ast.parse = self._orig_ast_parse  # type: ignore[assignment]
        if self._orig_re_compile is not None:
            re.compile = self._orig_re_compile  # type: ignore[assignment]


def _byte_len(data: Any) -> int:
    if data is None:
        return 0
    if isinstance(data, bytes):
        return len(data)
    if isinstance(data, bytearray):
        return len(data)
    if isinstance(data, memoryview):
        return data.nbytes
    if isinstance(data, str):
        return len(data.encode("utf-8"))
    try:
        return len(data)
    except Exception:
        return len(str(data).encode("utf-8"))


def csi_meter_v1() -> CSIMeter:
    """Return a CSI meter context manager."""
    return CSIMeter()


__all__ = ["CSIMeter", "csi_meter_v1"]
