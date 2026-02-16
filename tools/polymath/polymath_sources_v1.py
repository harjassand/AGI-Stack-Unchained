#!/usr/bin/env python3
"""Internet source adapters for polymath scout/bootstrap (v1)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from tools.polymath.polymath_dataset_fetch_v1 import fetch_url_sealed, load_blob_bytes

OPENALEX_TOPICS_URL = "https://api.openalex.org/topics"
ARXIV_QUERY_URL = "http://export.arxiv.org/api/query"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"
SEMANTIC_SCHOLAR_PAPER_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


class PolymathSourceClient:
    """Thin wrapper over sealed URL fetches for public science APIs."""

    def __init__(
        self,
        *,
        store_root: Path | None = None,
        allowed_hosts: tuple[str, ...] | list[str] | None = None,
        max_response_bytes: int | None = None,
    ) -> None:
        self._store_root = store_root
        self._allowed_hosts = tuple(sorted({str(value).strip().lower() for value in (allowed_hosts or []) if str(value).strip()}))
        self._max_response_bytes = None if max_response_bytes is None else max(1, int(max_response_bytes))

    def openalex_topics(
        self,
        *,
        page: int = 1,
        per_page: int = 50,
        sort: str = "cited_by_count:desc",
        mailto: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "page": str(max(1, int(page))),
            "per_page": str(max(1, int(per_page))),
            "sort": str(sort),
        }
        if mailto:
            params["mailto"] = str(mailto)
        sealed = fetch_url_sealed(
            OPENALEX_TOPICS_URL,
            params=params,
            store_root=self._store_root,
            allowed_hosts=self._allowed_hosts or None,
            max_bytes=self._max_response_bytes,
        )
        payload = self._load_json_from_sealed(sealed)
        return {
            "api": "openalex_topics",
            "payload": payload,
            "sealed": sealed,
            "url": str(sealed.get("url", OPENALEX_TOPICS_URL)),
        }

    def arxiv_query(
        self,
        *,
        search_query: str,
        start: int = 0,
        max_results: int = 25,
    ) -> dict[str, Any]:
        params = {
            "search_query": str(search_query),
            "start": str(max(0, int(start))),
            "max_results": str(max(1, int(max_results))),
        }
        sealed = fetch_url_sealed(
            ARXIV_QUERY_URL,
            params=params,
            store_root=self._store_root,
            allowed_hosts=self._allowed_hosts or None,
            max_bytes=self._max_response_bytes,
        )
        xml_text = load_blob_bytes(sha256=str(sealed["sha256"]), store_root=self._store_root).decode("utf-8", errors="replace")
        return {
            "api": "arxiv_query",
            "payload": {"xml": xml_text},
            "sealed": sealed,
            "url": str(sealed.get("url", ARXIV_QUERY_URL)),
        }

    def crossref_works(
        self,
        *,
        query: str,
        rows: int = 20,
        mailto: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "query": str(query),
            "rows": str(max(1, int(rows))),
        }
        if mailto:
            params["mailto"] = str(mailto)
        sealed = fetch_url_sealed(
            CROSSREF_WORKS_URL,
            params=params,
            store_root=self._store_root,
            allowed_hosts=self._allowed_hosts or None,
            max_bytes=self._max_response_bytes,
        )
        payload = self._load_json_from_sealed(sealed)
        return {
            "api": "crossref_works",
            "payload": payload,
            "sealed": sealed,
            "url": str(sealed.get("url", CROSSREF_WORKS_URL)),
        }

    def semantic_scholar_paper_search(
        self,
        *,
        query: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        params = {
            "query": str(query),
            "limit": str(max(1, int(limit))),
            "fields": "paperId,title,year,citationCount",
        }
        sealed = fetch_url_sealed(
            SEMANTIC_SCHOLAR_PAPER_SEARCH_URL,
            params=params,
            store_root=self._store_root,
            allowed_hosts=self._allowed_hosts or None,
            max_bytes=self._max_response_bytes,
        )
        payload = self._load_json_from_sealed(sealed)
        return {
            "api": "semantic_scholar_paper_search",
            "payload": payload,
            "sealed": sealed,
            "url": str(sealed.get("url", SEMANTIC_SCHOLAR_PAPER_SEARCH_URL)),
        }

    @staticmethod
    def dataset_source_hints(topic_name: str) -> list[dict[str, str]]:
        text = str(topic_name).strip().lower()
        hints: list[dict[str, str]] = []
        if any(token in text for token in ("genom", "dna", "rna", "virus", "gene")):
            hints.append({"adapter": "ncbi_datasets_download_genome", "source": "ncbi"})
            hints.append({"adapter": "uniprot_fetch_entry", "source": "uniprot"})
        if any(token in text for token in ("chem", "molecule", "compound", "drug")):
            hints.append({"adapter": "pubchem_fetch_compound", "source": "pubchem"})
        if not hints:
            hints.append({"adapter": "huggingface_load_dataset", "source": "huggingface"})
        return hints

    def _load_json_from_sealed(self, sealed: dict[str, Any]) -> dict[str, Any]:
        raw = load_blob_bytes(sha256=str(sealed["sha256"]), store_root=self._store_root)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("SCHEMA_FAIL")
        return payload


def main() -> None:
    parser = argparse.ArgumentParser(prog="polymath_sources_v1")
    parser.add_argument("--api", required=True, choices=["openalex", "arxiv", "crossref", "s2"])
    parser.add_argument("--query", default="")
    parser.add_argument("--mailto", default="")
    parser.add_argument("--per_page", type=int, default=25)
    parser.add_argument("--rows", type=int, default=20)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--store_root", default="")
    args = parser.parse_args()

    store_root = Path(args.store_root).resolve() if str(args.store_root).strip() else None
    client = PolymathSourceClient(store_root=store_root)

    if args.api == "openalex":
        result = client.openalex_topics(per_page=max(1, int(args.per_page)), mailto=str(args.mailto).strip() or None)
    elif args.api == "arxiv":
        query = str(args.query).strip() or "all:science"
        result = client.arxiv_query(search_query=query, max_results=max(1, int(args.limit)))
    elif args.api == "crossref":
        query = str(args.query).strip() or "science"
        result = client.crossref_works(query=query, rows=max(1, int(args.rows)), mailto=str(args.mailto).strip() or None)
    else:
        query = str(args.query).strip() or "science"
        result = client.semantic_scholar_paper_search(query=query, limit=max(1, int(args.limit)))

    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
