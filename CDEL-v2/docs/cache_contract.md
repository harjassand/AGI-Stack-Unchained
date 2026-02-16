Cache Contract (v1)

Purpose
  The closure cache is a performance optimization only. It must not change
  semantic results. Cached and uncached evaluations over the same dependency
  closure must produce identical outputs.

Cache Key (closure cache)
  The cache is indexed by:
  - ledger head hash (content-addressed state)
  - root symbol name (single-symbol closure)

  Key tuple:
    (head_hash, root_symbol)

Cache Value (closure cache)
  A JSON object with:
  - symbols: sorted list of symbol names in the dependency closure
  - modules: sorted list of module hashes needed for the closure

Closure Identity
  For audits and repro, we define a closure identity hash as:
    SHA-256(joined sorted module hashes, newline-delimited)

Determinism Requirements
  - Closure sets and module lists must be deterministically ordered.
  - JSON serialization uses stable ordering.
  - Cache hits/misses are treated as performance metadata only and must not
    affect evaluation outputs.

Claims Normalization (C7)
  - Only performance counters (cache hits/misses, index lookups) may be ignored.
  - Semantic outcome fields (accept/reject decision, rejection code, cost,
    spec work, and budget) are always compared.
  - If a report contains duplicate entries for the same task_id:
      * identical semantic entries are collapsed
      * any semantic mismatch is treated as data corruption and fails C7
