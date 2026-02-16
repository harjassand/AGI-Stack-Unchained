# CDEL Spec Checking v1

This document defines spec checking for v1.

## Supported spec kind

`forall`, `proof`, `proof_unbounded`, and `stat_cert` specs are supported:

- `vars`: typed variables
- `domain`: bounded enumeration parameters
- `assert`: term AST that must evaluate to Bool
- `goal`: proof goal (for `proof` / `proof_unbounded`)
- `proof`: proof term (for `proof` / `proof_unbounded`)
- `stat_cert`: sealed certificate that is signature-verified and checked
  against a global alpha-spending schedule
  - e-value is recomputed from `n` + `diff_sum` with bounds `[-1,1]`
  - e-value recomputation uses fixed-precision decimal math (no floats)

## Domain enumeration

For each variable type:

- Int: all integers in `[int_min, int_max]`
- Bool: `{false, true}`
- List[T]: all lists up to length `list_max_len` using the element domain
- Option[T]: `none` plus `some(v)` for each element in the element domain
- Pair[A,B]: cartesian product of the left/right domains
- Fun[A -> B]: must use `fun_symbols` only (finite list of existing symbols)

Function variables are instantiated only from `fun_symbols` whose type
matches exactly. No other higher-order enumeration is supported in v1.

## Evaluation model

- Deterministic, call-by-value evaluator
- Shared step limit across each assertion evaluation
- If evaluation exceeds the step limit, spec checking fails

## Rejections

Spec checking fails if:

- `assert` does not evaluate to Bool
- any assignment violates the assertion
- domain bounds are invalid (e.g. int_min > int_max)
- function domain is empty or references unknown symbols
- proof terms are missing or invalid for `proof` / `proof_unbounded`
- stat cert signature is invalid or alpha schedule is violated
- stat cert alpha_schedule does not match config
- stat cert harness hashes do not match config
- stat cert key_id is not in the allowed key set
