# MetaLang IR v1

MetaLang IR is a total, deterministic, JSON-encoded IR. All IR JSON must be GCJ-1 admissible.

## Types

Primitive types:

- `i64`
- `bool`
- `bytes` (base64-encoded in JSON)
- `string`

Composite types:

- `list[T]`
- `map[string -> T]`

No recursion, no function pointers, no reflection.

## JSON AST format

Each expression is encoded as an object with exactly one key, where the key is the constructor name.

Constants:

- `{"Int": 123}`
- `{"Bool": true}`
- `{"Bytes": "<base64>"}`
- `{"Str": "..."}`
- `{"Safe": null}` (kernel builtin; only valid in acceptance IR)

Variables and binding:

- `{"Var": "x"}`
- `{"Let": {"name": "x", "value": <expr>, "body": <expr>}}`

Control:

- `{"If": {"cond": <expr>, "then": <expr>, "else": <expr>}}`
- `{"And": [<expr>, ...]}`
- `{"Or": [<expr>, ...]}`
- `{"Not": <expr>}`

Comparisons (ints only):

- `{"Eq": [<expr>, <expr>]}`
- `{"Neq": [<expr>, <expr>]}`
- `{"Lt": [<expr>, <expr>]}`
- `{"Le": [<expr>, <expr>]}`
- `{"Gt": [<expr>, <expr>]}`
- `{"Ge": [<expr>, <expr>]}`

Map/list ops:

- `{"MapGet": [<expr>, <expr>, <expr>]}`
- `{"MapHas": [<expr>, <expr>]}`
- `{"ListGet": [<expr>, <expr>, <expr>]}`
- `{"ListLen": <expr>}`

Builtins:

- `{"Sha256": <expr>}`
- `{"BytesConcat": [<expr>, ...]}`

Bounded loop:

```
{"ForRange": {
  "var": "i",
  "start": 0,
  "end": 10,
  "fuel": 10,
  "init": <expr>,
  "body": <expr>
}}
```

`ForRange` evaluates `init` to get `acc`, then iterates `i` from `start` to `end - 1`.
In the body, the loop variable is bound to `var` and the accumulator is bound to `acc`.
Each iteration consumes 1 unit of fuel. If fuel reaches 0, evaluation fails.

## Determinism

- Evaluation is pure and deterministic.
- Any runtime error (type error, missing var, fuel/gas exhaustion) ⇒ INVALID.
- Map iteration uses sorted key order (Unicode codepoint order).

## Gas accounting

- Every AST node evaluation costs **1 gas** plus child costs.
- `Sha256` costs `50 + ceil(len(bytes)/64)` additional gas.
- `ForRange` costs 1 gas per iteration in addition to body costs.
- Exceeding `max_gas` ⇒ INVALID.

Exact limits are loaded from `meta_constitution/v1/spec/ir_limits.json`.
