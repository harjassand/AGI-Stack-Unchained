#!/usr/bin/env python3
"""Deterministic sealed websearch adapters (v1)."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Iterable, Mapping

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from tools.polymath.polymath_dataset_fetch_v1 import fetch_url_sealed, load_blob_bytes

_DUCKDUCKGO_API_URL = "https://api.duckduckgo.com/"
_WIKIPEDIA_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
_DUCKDUCKGO_ALLOWED_HOSTS = ["api.duckduckgo.com"]
_WIKIPEDIA_ALLOWED_HOSTS = ["en.wikipedia.org"]
_DEFAULT_MAX_BYTES = 2 * 1024 * 1024
_MAX_TOP_K = 10


def _normalize_query(value: str) -> str:
    text = " ".join(str(value).strip().split())
    if not text:
        raise RuntimeError("SCHEMA_FAIL")
    return text


def _normalize_top_k(value: int) -> int:
    return max(1, min(_MAX_TOP_K, int(value)))


def _strip_html_text(value: str) -> str:
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.strip().split())


def _canonical_results(rows: Iterable[Mapping[str, Any]], *, top_k: int) -> list[dict[str, str]]:
    dedup: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        title = " ".join(str(row.get("title", "")).strip().split())
        url = " ".join(str(row.get("url", "")).strip().split())
        snippet = " ".join(str(row.get("snippet", "")).strip().split())
        if not title and url:
            title = url
        if not url:
            continue
        key = (title, url, snippet)
        dedup[key] = {
            "snippet": snippet,
            "title": title,
            "url": url,
        }
    ordered = sorted(
        dedup.values(),
        key=lambda row: (
            str(row.get("title", "")).lower(),
            str(row.get("url", "")).lower(),
            str(row.get("snippet", "")).lower(),
        ),
    )
    return ordered[: max(1, int(top_k))]


def _sealed_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "bytes_path": str(row.get("bytes_path", "")),
        "cached_b": bool(row.get("cached_b", False)),
        "receipt_path": str(row.get("receipt_path", "")),
        "sha256": str(row.get("sha256", "")),
        "url": str(row.get("url", "")),
    }


def _load_payload_json(*, sealed: Mapping[str, Any], store_root: Path | None) -> dict[str, Any]:
    raw = load_blob_bytes(sha256=str(sealed.get("sha256", "")), store_root=store_root)
    payload = json.loads(raw.decode("utf-8", errors="strict"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _duckduckgo_rows(payload: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    heading = " ".join(str(payload.get("Heading", "")).strip().split())
    abstract_text = _strip_html_text(str(payload.get("AbstractText", "")))
    abstract_url = " ".join(str(payload.get("AbstractURL", "")).strip().split())
    if heading and abstract_url:
        rows.append(
            {
                "title": heading,
                "url": abstract_url,
                "snippet": abstract_text,
            }
        )

    def _ingest_topics(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                _ingest_topics(item)
            return
        if not isinstance(value, dict):
            return
        nested = value.get("Topics")
        if isinstance(nested, list):
            _ingest_topics(nested)
        text = _strip_html_text(str(value.get("Text", "")))
        first_url = " ".join(str(value.get("FirstURL", "")).strip().split())
        if text and first_url:
            title = text.split(" - ", 1)[0].strip()
            rows.append(
                {
                    "title": title or text,
                    "url": first_url,
                    "snippet": text,
                }
            )

    _ingest_topics(payload.get("Results"))
    _ingest_topics(payload.get("RelatedTopics"))
    return rows


def _wikipedia_rows(payload: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    query_obj = payload.get("query")
    search_rows = query_obj.get("search") if isinstance(query_obj, dict) else None
    if not isinstance(search_rows, list):
        return rows
    for row in search_rows:
        if not isinstance(row, dict):
            continue
        title = " ".join(str(row.get("title", "")).strip().split())
        if not title:
            continue
        pageid = row.get("pageid")
        if isinstance(pageid, int) and pageid > 0:
            url = f"https://en.wikipedia.org/?curid={int(pageid)}"
        else:
            url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="")
        snippet = _strip_html_text(str(row.get("snippet", "")))
        rows.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
            }
        )
    return rows


def duckduckgo_search(
    *,
    query: str,
    top_k: int = 5,
    store_root: Path | None = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    query_norm = _normalize_query(query)
    top_k_norm = _normalize_top_k(top_k)
    sealed = fetch_url_sealed(
        _DUCKDUCKGO_API_URL,
        params={
            "format": "json",
            "no_html": "1",
            "q": query_norm,
            "skip_disambig": "1",
        },
        store_root=store_root,
        allowed_hosts=_DUCKDUCKGO_ALLOWED_HOSTS,
        max_bytes=max(1, int(max_bytes)),
    )
    payload = _load_payload_json(sealed=sealed, store_root=store_root)
    results = _canonical_results(_duckduckgo_rows(payload), top_k=top_k_norm)
    return {
        "sealed": _sealed_ref(sealed),
        "summary": {
            "provider": "duckduckgo",
            "query": query_norm,
            "results": results,
            "top_k_u64": int(top_k_norm),
        },
    }


def wikipedia_search(
    *,
    query: str,
    top_k: int = 5,
    store_root: Path | None = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    query_norm = _normalize_query(query)
    top_k_norm = _normalize_top_k(top_k)
    sealed = fetch_url_sealed(
        _WIKIPEDIA_SEARCH_URL,
        params={
            "action": "query",
            "format": "json",
            "list": "search",
            "srlimit": str(int(top_k_norm)),
            "srsearch": query_norm,
        },
        store_root=store_root,
        allowed_hosts=_WIKIPEDIA_ALLOWED_HOSTS,
        max_bytes=max(1, int(max_bytes)),
    )
    payload = _load_payload_json(sealed=sealed, store_root=store_root)
    results = _canonical_results(_wikipedia_rows(payload), top_k=top_k_norm)
    return {
        "sealed": _sealed_ref(sealed),
        "summary": {
            "provider": "wikipedia",
            "query": query_norm,
            "results": results,
            "top_k_u64": int(top_k_norm),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="polymath_websearch_v1")
    parser.add_argument("--provider", required=True, choices=("duckduckgo", "wikipedia"))
    parser.add_argument("--query", required=True)
    parser.add_argument("--top_k", type=int, default=5)
    parser.add_argument("--store_root", default="")
    parser.add_argument("--max_bytes", type=int, default=_DEFAULT_MAX_BYTES)
    args = parser.parse_args()

    store_root = Path(args.store_root).expanduser().resolve() if str(args.store_root).strip() else None
    if str(args.provider) == "duckduckgo":
        payload = duckduckgo_search(
            query=str(args.query),
            top_k=int(args.top_k),
            store_root=store_root,
            max_bytes=max(1, int(args.max_bytes)),
        )
    else:
        payload = wikipedia_search(
            query=str(args.query),
            top_k=int(args.top_k),
            store_root=store_root,
            max_bytes=max(1, int(args.max_bytes)),
        )
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
