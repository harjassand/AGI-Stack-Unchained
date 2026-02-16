from __future__ import annotations

from pathlib import Path

import pytest

from tools.polymath import polymath_dataset_fetch_v1 as fetch_v1


class _FakeResponse:
    def __init__(self, data: bytes, *, status: int = 200, headers: dict[str, str] | None = None) -> None:
        self._data = data
        self._offset = 0
        self.status = int(status)
        self.headers = dict(headers or {"Content-Type": "application/json", "Content-Length": str(len(data))})

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return False

    def read(self, size: int = -1) -> bytes:
        if size is None or int(size) < 0:
            if self._offset >= len(self._data):
                return b""
            out = self._data[self._offset :]
            self._offset = len(self._data)
            return out
        start = self._offset
        end = min(len(self._data), start + int(size))
        self._offset = end
        return self._data[start:end]


def test_cache_miss_net_disabled_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMEGA_NET_LIVE_OK", raising=False)
    with pytest.raises(RuntimeError, match="NET_DISABLED"):
        fetch_v1.fetch_url_sealed(
            "https://example.com/data.json",
            store_root=tmp_path / "store",
            allowed_hosts=["example.com"],
        )


def test_cache_hit_allowed_when_net_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store_root = tmp_path / "store"
    calls = {"count": 0}

    def _fake_urlopen(request, timeout=45):  # noqa: ANN001, ARG001
        calls["count"] += 1
        return _FakeResponse(b'{"ok":true}')

    monkeypatch.setenv("OMEGA_NET_LIVE_OK", "1")
    monkeypatch.setattr(fetch_v1.urllib.request, "urlopen", _fake_urlopen)

    first = fetch_v1.fetch_url_sealed(
        "https://example.com/data.json",
        store_root=store_root,
        allowed_hosts=["example.com"],
    )
    assert bool(first.get("cached_b", True)) is False
    assert calls["count"] == 1

    monkeypatch.delenv("OMEGA_NET_LIVE_OK", raising=False)
    second = fetch_v1.fetch_url_sealed(
        "https://example.com/data.json",
        store_root=store_root,
        allowed_hosts=["example.com"],
    )
    assert bool(second.get("cached_b", False)) is True
    assert calls["count"] == 1


def test_net_enabled_fetches_and_seals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store_root = tmp_path / "store"

    def _fake_urlopen(request, timeout=45):  # noqa: ANN001, ARG001
        return _FakeResponse(b'{"rows":[1,2,3]}')

    monkeypatch.setenv("OMEGA_NET_LIVE_OK", "1")
    monkeypatch.setattr(fetch_v1.urllib.request, "urlopen", _fake_urlopen)

    result = fetch_v1.fetch_url_sealed(
        "https://example.com/data.json",
        store_root=store_root,
        allowed_hosts=["example.com"],
    )
    assert bool(result.get("cached_b", True)) is False
    bytes_path = Path(str(result.get("bytes_path", "")))
    receipt_path = Path(str(result.get("receipt_path", "")))
    assert bytes_path.exists() and bytes_path.is_file()
    assert receipt_path.exists() and receipt_path.is_file()
