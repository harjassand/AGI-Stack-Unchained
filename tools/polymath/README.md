# Polymath Tools (v1)

`tools/polymath/` provides deterministic, sealed-data tooling for Phase-16 polymath workflows.

- `polymath_dataset_fetch_v1.py`: fetch URL bytes into `polymath/store/blobs/sha256/` + append-only fetch receipts.
- `polymath_sources_v1.py`: source adapters for OpenAlex, arXiv, Crossref, and Semantic Scholar using sealed fetches.
- `polymath_scout_v1.py`: computes deterministic void scores and appends `polymath_void_report_v1` rows.
- `polymath_domain_bootstrap_v1.py`: bootstraps a domain scaffold, domain pack, corpus, and baseline solver.
- `polymath_domain_corpus_v1.py`: builds pinned compact corpora from sealed test splits.
- `polymath_equivalence_suite_v1.py`: verifies candidate/reference outputs under the polymath verifier kernel.

## Store Layout

- `polymath/store/blobs/sha256/<digest>`: immutable content-addressed bytes.
- `polymath/store/receipts/*.json`: fetch receipts (append-only; never overwritten).
- `polymath/store/indexes/urls_to_sha256.jsonl`: request-hash to blob hash links.
- `polymath/store/indexes/domain_to_artifacts.jsonl`: domain artifact index.

## Quick Start

```bash
python3 tools/polymath/polymath_scout_v1.py \
  --registry_path polymath/registry/polymath_domain_registry_v1.json \
  --void_report_path polymath/registry/polymath_void_report_v1.jsonl \
  --mailto you@example.com
```
