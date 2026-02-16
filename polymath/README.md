# Polymath (v18.0)

Polymath is the AGI-Stack module for deterministic domain discovery, bootstrap, and conquest.
It discovers candidate scientific domains, builds deterministic domain artifacts, and produces verified campaign promotions for the Omega daemon.

This file describes the repository pieces that are currently present and how they are intended to be used together.

## Module role and trust boundaries

- Reusable domain state and artifacts are under `polymath/` and `domains/`.
- Campaign orchestration and promotion rules run through `campaigns/` and `CDEL-v2/`.
- Deterministic substrate and canonicalization are enforced by the existing RE2-like pipeline used by this repository.
- Trust boundaries described in this repo are unchanged: RE1–RE4 are not altered by this module’s own changes.

## Directory layout

```text
polymath/
├── domain_policy_v1.json
├── registry/
│   ├── polymath_domain_registry_v1.json
│   ├── polymath_portfolio_v1.json
│   ├── polymath_scout_status_v1.json
│   ├── polymath_void_report_v1.jsonl
│   └── void_topic_router_v1.json
└── store/
    ├── indexes/
    │   ├── urls_to_sha256.jsonl
    │   └── domain_to_artifacts.jsonl
    ├── blobs/
    └── receipts/

domains/
└── pubchem_weight300/
    ├── domain_pack_l0_v1.json
    ├── domain_pack_l1_v1.json
    ├── domain_pack_l2_v1.json
    ├── schemas/
    ├── solver/
    ├── corpus/
    └── README.md

tools/polymath/
├── polymath_dataset_fetch_v1.py
├── polymath_domain_bootstrap_v1.py
├── polymath_domain_corpus_v1.py
├── polymath_equivalence_suite_v1.py
├── polymath_refinery_proposer_v1.py
├── polymath_seed_flagships_v1.py
├── polymath_scout_v1.py
├── polymath_sources_v1.py
├── polymath_void_to_goals_v1.py
└── polymath_build_flagship_pubchem_weight300_v1.py
```

## Core data contracts

### `polymath/domain_policy_v1.json`

- `schema_version`: `domain_policy_v1`
- `allowlist_keywords`: inclusion gate for policy-eligible topics
- `denylist_keywords`: exclusion gate

### `polymath/registry/polymath_domain_registry_v1.json`

- `schema_version`: `polymath_domain_registry_v1`
- `domains`: array of registry rows
- Required row fields used by campaigns: `domain_id`, `domain_name`, `status`, `created_at_utc`, `domain_pack_rel`, `topic_ids`, `capability_id`, `ready_for_conquer`, `ready_for_conquer_reason`, and `conquered_b`.

### `polymath/registry/polymath_scout_status_v1.json`

- `schema_version`: `polymath_scout_status_v1`
- Tracks the latest scout run with `scout_run_id`, `tick_u64`, `rows_written_u64`, `topics_scanned_u64`, `top_void_score_q32`, and `sources_sha256s`.

### `polymath/registry/polymath_void_report_v1.jsonl`

- `schema_version`: `polymath_void_report_v1`
- Each line is one candidate row with at least `candidate_domain_id`, `topic_id`, `topic_name`, `trend_score_q32`, `coverage_score_q32`, `void_score_q32`, `source_evidence`, and `row_id`.

### `polymath/registry/polymath_portfolio_v1.json`

- `schema_version`: `polymath_portfolio_v1`
- Aggregates conquered and attempted domains using `domains` and `portfolio_score_q32`.

### `polymath/registry/void_topic_router_v1.json`

- Maps topic IDs to routes: `SCIENCE` → `RSI_BOUNDLESS_SCIENCE_V9`, `MATH` → `RSI_BOUNDLESS_MATH_V8`.
- Supports explicit overrides and keyword rules.

## Lifecycle: scout → bootstrap → conquer

### 1) Scout

- Script: `tools/polymath/polymath_scout_v1.py`
- Campaign: `campaigns/rsi_polymath_scout_v1`
- Inputs:
  - existing registry rows
  - policy rules
- Output:
  - `polymath/registry/polymath_void_report_v1.jsonl`
  - `polymath/registry/polymath_scout_status_v1.json`
  - campaign report + promotion bundle in `daemon/rsi_polymath_scout_v1/state/`

### 2) Bootstrap

- Script: `tools/polymath/polymath_seed_flagships_v1.py` (store seeding helper)
- Campaign: `campaigns/rsi_polymath_bootstrap_domain_v1`
- Input:
  - top candidate from void report
- Output:
  - new domain pack under `domains/<domain_id>/`
  - updated registry row (`conquered_b=false`, `ready_for_conquer=true`)
  - `daemon/rsi_polymath_bootstrap_domain_v1/state/reports/polymath_bootstrap_report_v1.json`
  - `daemon/rsi_polymath_bootstrap_domain_v1/state/promotion/*.polymath_bootstrap_promotion_bundle_v1.json`

### 3) Conquer

- Campaign: `campaigns/rsi_polymath_conquer_domain_v1`
- Input:
  - active registry rows
- Output:
  - baseline/improved outputs in `domains/<domain_id>/corpus/`
  - conquest report in `daemon/rsi_polymath_conquer_domain_v1/state/reports/polymath_conquer_report_v1.json`
  - conquest promotion bundle in `daemon/rsi_polymath_conquer_domain_v1/state/promotion/*.polymath_conquer_promotion_bundle_v1.json`
- Conquer updates:
  - `ready_for_conquer` flag
  - `conquered_b` marker
  - portfolio entry / cache-hit accounting

## Deterministic conventions used in this module

- Canonical JSON encoding is used wherever payloads are emitted through project helpers.
- Q32 fixed-point values are used for scores; binary serializations in store helpers are content-addressed by SHA-256.
- IDs and IDs-in-derived payloads are hash-derived and stable for fixed inputs.
- No reliance on mutable ordering of dicts in hash-sensitive operations.
- All listed path fields are repo-relative and POSIX-style.
- `polymath_store_root` defaults to `.omega_cache/polymath/store`, with fallback to `polymath/store`.

## Campaign output schema IDs to track

- `polymath_scout_promotion_bundle_v1`
- `polymath_bootstrap_report_v1`
- `polymath_bootstrap_promotion_bundle_v1`
- `polymath_conquer_report_v1`
- `polymath_conquer_promotion_bundle_v1`
- `polymath_scout_report_v1`
- `polymath_domain_pack_v1`
- `polymath_candidate_outputs_v1`
- `polymath_equivalence_report_v1`

Schema files (when present) live under `Genesis/schema/v18_0/`.

## Campaign metrics surfaced to observers

- `domain_coverage_ratio`
- `top_void_score_q32`
- `domains_ready_for_conquer_u64`
- `polymath_last_scout_tick_u64`
- `polymath_scout_age_ticks_u64`
- `polymath_portfolio_score_q32`
- `polymath_portfolio_domains_u64`
- `polymath_portfolio_cache_hit_rate_q32`

## Command reference

### Scout void candidates

```bash
python3 tools/polymath/polymath_scout_v1.py \
  --registry_path polymath/registry/polymath_domain_registry_v1.json \
  --store_root .omega_cache/polymath/store \
  --mailto you@example.com \
  --max_topics 12
```

### Seed flagship corpus into store

```bash
python3 tools/polymath/polymath_seed_flagships_v1.py \
  --store_root .omega_cache/polymath/store \
  --summary_path /tmp/polymath_seed_summary.json
```

### Build refinery proposals

```bash
python3 tools/polymath/polymath_refinery_proposer_v1.py \
  --registry_path polymath/registry/polymath_domain_registry_v1.json \
  --store_root .omega_cache/polymath/store \
  --workers 4 \
  --max_domains 32 \
  --summary_path /tmp/polymath_proposals.json
```

### Convert high-void topics to goals

```bash
python3 tools/polymath/polymath_void_to_goals_v1.py \
  --out_goal_queue_effective_path /tmp/goal_queue_v1.json \
  --tick_u64 123 \
  --max_goals 2
```

### Build pubchem flagship packs

```bash
python3 tools/polymath/polymath_build_flagship_pubchem_weight300_v1.py \
  --fixture_path tools/polymath/fixtures/pubchem_weight300_snapshot_v1.json \
  --domain_root domains/pubchem_weight300 \
  --store_root .omega_cache/polymath/store
```

## Campaign runs for reproducible verification

### Run polymath campaigns directly

```bash
python3 -m cdel.v18_0.campaign_polymath_scout_v1 \
  --campaign_pack campaigns/rsi_polymath_scout_v1/rsi_polymath_scout_pack_v1.json \
  --out_dir /tmp/polymath_scout_run

python3 -m cdel.v18_0.campaign_polymath_bootstrap_domain_v1 \
  --campaign_pack campaigns/rsi_polymath_bootstrap_domain_v1/rsi_polymath_bootstrap_domain_pack_v1.json \
  --out_dir /tmp/polymath_bootstrap_run

python3 -m cdel.v18_0.campaign_polymath_conquer_domain_v1 \
  --campaign_pack campaigns/rsi_polymath_conquer_domain_v1/rsi_polymath_conquer_domain_pack_v1.json \
  --out_dir /tmp/polymath_conquer_run
```

Run paths to inspect after each campaign:
- Scout report: `daemon/rsi_polymath_scout_v1/state/reports/polymath_scout_report_v1.json`
- Bootstrap report: `daemon/rsi_polymath_bootstrap_domain_v1/state/reports/polymath_bootstrap_report_v1.json`
- Conquer report: `daemon/rsi_polymath_conquer_domain_v1/state/reports/polymath_conquer_report_v1.json`
- Promotion bundle: `daemon/rsi_polymath_*_domain_v1/state/promotion/*.polymath_*_promotion_bundle_v1.json`

## Store and artifact notes

- Sealed fetches are recorded in `polymath/store/receipts/` and `polymath/store/indexes/*.jsonl`.
- Source bytes are stored under `polymath/store/blobs/sha256/<digest>`.
- `load_blob_bytes` and verifier checks rely on SHA-256 byte identity and receipt matching.
- Store directories are immutable by design: existing blob overwrite is rejected unless digest matches.

## Recommended operational playbook

- Keep `polymath/store` under the repo and version control policy separate from generated campaign run directories.
- Run scout, then seed, then bootstrap/conquer; use proposal index cache in `store/refinery/indexes/` when available.
- Prefer running campaigns through the Omega daemon profiles in `campaigns/` for production-mode policy coupling.
- Validate outputs using the corresponding `verify_rsi_*_v1.py` modules before adoption flow.

## Environment variables commonly used by polymath

- `OMEGA_POLYMATH_STORE_ROOT` overrides store location.
- `OMEGA_TICK_U64` drives tick-dependent scout/conquer reporting behavior.
- `OMEGA_NET_LIVE_OK=1` enables live fetches in `polymath_dataset_fetch_v1.py`; otherwise fetches use cache.
- `OMEGA_RUN_SEED_U64` is included in offline scout fallback evidence.

## Related references

- `campaigns/README.md`
- `tools/polymath/README.md`
- `CDEL-v2/cdel/v18_0/verify_rsi_polymath_scout_v1.py`
- `CDEL-v2/cdel/v18_0/campaign_polymath_scout_v1.py`
- `CDEL-v2/cdel/v18_0/campaign_polymath_bootstrap_domain_v1.py`
- `CDEL-v2/cdel/v18_0/campaign_polymath_conquer_domain_v1.py`

---

Generated with deterministic, campaign-path aligned conventions.
