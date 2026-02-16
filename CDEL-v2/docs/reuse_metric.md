Reuse Metrics (v1)

Unit of analysis
  - Per accepted Δ (module)
  - Per-run aggregates over accepted modules

Primary metric: external reference ratio
  For each accepted Δ:
    1) Parse all definitions in D_Δ.
    2) Collect referenced symbols (sym nodes), excluding primitives/builtins.
    3) Partition references into:
         R_old: symbols defined in earlier modules
         R_new: symbols defined within Δ
    4) Compute:
         reuse_ratio(Δ) = |R_old| / (|R_old| + |R_new|)
       If denominator is 0, define reuse_ratio(Δ) = 0 and log denom_zero.

Secondary metric: forward reuse rate
  For each symbol s defined at step i:
    forward_used(s) = 1 if any later accepted module references s
  Then:
    forward_reuse_rate = (# symbols with forward_used=1) / (total new symbols)

Aggregation
  - Report mean + median reuse_ratio across accepted Δ
  - Report final-window average reuse_ratio over the last 20% of accepted Δ
  - Report forward_reuse_rate

Exclusions
  - Primitives/builtins are excluded (not sym nodes).
  - Self-reference counts as R_new only if it appears in a body (not the definition head).
