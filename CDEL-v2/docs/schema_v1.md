# CDEL Schema v1 (Module + AST)

This document is the schema of record for v1 modules and ASTs.

## Module JSON (input to `cdel verify` / `cdel commit`)

Top-level object:

- `schema_version`: integer, must be 1
- `dsl_version`: integer, must be 1
- `parent`: string hash of prior module payload (or `GENESIS`)
- `payload`: object (hashed; see canon spec)
- `meta`: object (optional, not hashed)

### Payload object (hashed)

- `new_symbols`: array of strings (unique)
- `definitions`: array of definition objects (unique names, same set as `new_symbols`)
- `declared_deps`: array of strings (unique)
- `specs`: array of spec objects (may be empty)
- `concepts`: array of concept tags (optional; defaults to empty)
- `capacity_claim`: object (optional)
  - `ast_nodes`: int
  - `spec_work`: int
  - `index_impact`: int

### Definition object

- `name`: string
- `params`: array of params
  - `name`: string
  - `type`: type object
- `ret_type`: type object
- `body`: term AST node
- `termination`: object
  - `kind`: string (v1 supports `structural` for recursive defs)
  - `decreases_param`: string or null

### Spec object

- `kind`: string (`forall`, `proof`, `proof_unbounded`)
- `vars`: array of vars (only for `forall`)
  - `name`: string
  - `type`: type object
- `domain`: object (only for `forall`)
  - `int_min`: int
  - `int_max`: int
  - `list_max_len`: int
  - `fun_symbols`: array of strings
- `assert`: term AST node (must evaluate to Bool; only for `forall`)
- `goal`: proof goal (only for `proof` / `proof_unbounded`)
- `proof`: proof term (only for `proof` / `proof_unbounded`)

### Concept tag object

- `concept`: string
- `symbol`: string (must be in `new_symbols`)

### Stat cert spec (`kind = "stat_cert"`)

- `concept`: string
- `metric`: string (`accuracy` in v1)
- `null`: string (`no_improvement` or `no_regression`)
- `baseline_symbol`: string
- `candidate_symbol`: string
- `eval`: object
  - `episodes`: int
  - `max_steps`: int
  - `paired_seeds`: bool
  - `oracle_symbol`: string (existing symbol)
  - `eval_harness_id`: string
  - `eval_harness_hash`: string
  - `eval_suite_hash`: string
- `risk`: object
  - `alpha_i`: string decimal
  - `evalue_threshold`: string decimal
  - `alpha_schedule`: object
    - `name`: string (v1 supports `p_series`)
    - `exponent`: int (>1)
    - `coefficient`: string decimal
- `certificate`: object
  - `evalue_schema_version`: int (must be `2`)
  - `n`: int
  - `baseline_successes`: int
  - `candidate_successes`: int
  - `diff_sum`: int
  - `diff_min`: int
  - `diff_max`: int
  - `evalue`: object
    - `mantissa`: string decimal (fixed precision, 1.x format)
    - `exponent10`: int (base-10 exponent)
  - `transcript_hash`: string
  - `signature`: string
  - `signature_scheme`: string
  - `key_id`: string

### Type object

- `{"tag":"int"}`
- `{"tag":"bool"}`
- `{"tag":"list","of": <type>}`
- `{"tag":"option","of": <type>}`
- `{"tag":"pair","left": <type>,"right": <type>}`
- `{"tag":"fun","args": [<type>,...],"ret": <type>}`

### Term AST nodes (v1)

Literals:
- `{"tag":"int","value": <int>}`
- `{"tag":"bool","value": <bool>}`
- `{"tag":"nil"}`
- `{"tag":"cons","head": <term>,"tail": <term>}`
- `{"tag":"none"}`
- `{"tag":"some","value": <term>}`
- `{"tag":"pair","left": <term>,"right": <term>}`
- `{"tag":"fst","pair": <term>}`
- `{"tag":"snd","pair": <term>}`

Variables and symbols:
- `{"tag":"var","name": <string>}`
- `{"tag":"sym","name": <string>}`

Control and application:
- `{"tag":"if","cond": <term>,"then": <term>,"else": <term>}`
- `{"tag":"app","fn": <term>,"args": [<term>,...]}`

Primitives:
- `{"tag":"prim","op":"add","args":[t1,t2]}`
- `{"tag":"prim","op":"sub","args":[t1,t2]}`
- `{"tag":"prim","op":"mul","args":[t1,t2]}`
- `{"tag":"prim","op":"mod","args":[t1,t2]}`
- `{"tag":"prim","op":"eq_int","args":[t1,t2]}`
- `{"tag":"prim","op":"lt_int","args":[t1,t2]}`
- `{"tag":"prim","op":"le_int","args":[t1,t2]}`
- `{"tag":"prim","op":"and","args":[t1,t2]}`
- `{"tag":"prim","op":"or","args":[t1,t2]}`
- `{"tag":"prim","op":"not","args":[t1]}`

List match:
```
{
  "tag":"match_list",
  "scrutinee": <term>,
  "nil_case": <term>,
  "cons_case": {"head_var": "h", "tail_var": "t", "body": <term>}
}
```

Option match:
```
{
  "tag":"match_option",
  "scrutinee": <term>,
  "none_case": <term>,
  "some_case": {"var": "v", "body": <term>}
}
```

## Typing rules (summary)

- `int` literal : Int
- `bool` literal : Bool
- `nil` : List[T] (requires expected type)
- `cons` : List[T] if head : T and tail : List[T]
- `none` : Option[T] (requires expected type)
- `some` : Option[T] if value : T
- `if` : branches must have same type; condition Bool
- `prim` : fixed signatures as per op
- `app` : function type A1 -> ... -> An -> R; args match A1..An
- `match_list` : scrutinee List[T]; cons branch binds head:T and tail:List[T]
- `pair` : Pair[A,B] if left:A and right:B
- `fst` : A from Pair[A,B]
- `snd` : B from Pair[A,B]
- `match_option` : scrutinee Option[T]; some branch binds value:T

## Hashed vs non-hashed

- Hashed: canonicalized `payload`
- Not hashed: `meta` and module wrapper fields (schema/dsl versions, parent)

The payload hash is the content address used in the ledger.
