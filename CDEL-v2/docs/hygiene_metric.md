Hygiene Metrics (v1)

Symbol graph
  Directed edges a -> b exist if definition of a references symbol b (sym node).

Public roots
  - All task target symbols (new_symbol or module payload new_symbols)
  - Core primitives (add, sub, mul, mod, eq_int, lt_int, le_int, and, or, not)
  - Optional exports chain if present (not used in v1)

Reachability and unused fraction
  reachable = nodes reachable from roots in the symbol graph
  unused_fraction = 1 - |reachable| / |total_symbols|

Hygiene delta claim
  Compare baseline vs reuse-pressure run:
    expected: unused_fraction decreases under reuse pressure
