from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.polymath import polymath_dataset_fetch_v1 as fetch_v1
from tools.polymath import polymath_websearch_v1 as websearch_v1


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


def _fake_urlopen(request, timeout=45):  # noqa: ANN001, ARG001
    url = str(getattr(request, "full_url", ""))
    if "duckduckgo.com" in url:
        payload = {
            "Heading": "OpenAI",
            "AbstractText": "OpenAI is an AI research lab.",
            "AbstractURL": "https://openai.com/",
            "RelatedTopics": [
                {
                    "Text": "GPT-4 - model family",
                    "FirstURL": "https://duckduckgo.com/GPT-4",
                },
                {
                    "Text": "ChatGPT - assistant",
                    "FirstURL": "https://duckduckgo.com/ChatGPT",
                },
            ],
        }
        return _FakeResponse(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    if "w/api.php" in url:
        payload = {
            "query": {
                "search": [
                    {
                        "title": "OpenAI",
                        "pageid": 61219369,
                        "snippet": "<span class=\"searchmatch\">OpenAI</span> research organization",
                    },
                    {
                        "title": "Artificial intelligence",
                        "pageid": 1164,
                        "snippet": "field of study",
                    },
                ]
            }
        }
        return _FakeResponse(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    raise RuntimeError(f"unexpected url in test: {url}")


def _canon_summary(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def test_websearch_seals_and_summaries_are_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store_root = tmp_path / "store"
    monkeypatch.setenv("OMEGA_NET_LIVE_OK", "1")
    monkeypatch.setattr(fetch_v1.urllib.request, "urlopen", _fake_urlopen)

    ddg_a = websearch_v1.duckduckgo_search(query="OpenAI", top_k=3, store_root=store_root)
    ddg_b = websearch_v1.duckduckgo_search(query="OpenAI", top_k=3, store_root=store_root)
    wiki_a = websearch_v1.wikipedia_search(query="OpenAI", top_k=2, store_root=store_root)
    wiki_b = websearch_v1.wikipedia_search(query="OpenAI", top_k=2, store_root=store_root)

    assert Path(str(ddg_a["sealed"]["bytes_path"])).exists()
    assert Path(str(ddg_a["sealed"]["receipt_path"])).exists()
    assert Path(str(wiki_a["sealed"]["bytes_path"])).exists()
    assert Path(str(wiki_a["sealed"]["receipt_path"])).exists()

    assert _canon_summary(ddg_a["summary"]) == _canon_summary(ddg_b["summary"])
    assert _canon_summary(wiki_a["summary"]) == _canon_summary(wiki_b["summary"])


def test_websearch_forbidden_host_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMEGA_NET_LIVE_OK", "1")
    monkeypatch.setattr(websearch_v1, "_DUCKDUCKGO_API_URL", "https://badhost.invalid/")
    with pytest.raises(RuntimeError, match="FORBIDDEN_HOST"):
        websearch_v1.duckduckgo_search(query="OpenAI", top_k=2, store_root=tmp_path / "store")


def test_websearch_net_disabled_on_cache_miss_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMEGA_NET_LIVE_OK", raising=False)
    with pytest.raises(RuntimeError, match="NET_DISABLED"):
        websearch_v1.wikipedia_search(query="OpenAI", top_k=2, store_root=tmp_path / "store")
