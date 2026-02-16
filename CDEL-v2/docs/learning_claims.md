# Learning, Risk Control, and Non-Interference

## What “learning” means in CDEL

Learning is the combination of:

1. **CDEL append**: immutable, verified definitions are appended to the ledger.
2. **CAL adoption**: certified, append-only routing decisions select which
   symbol is active for a concept.

No prior definition is mutated; behavior changes only via explicit adoption.

## Risk control statement (stat_cert + alpha spending)

Each accepted `stat_cert` spends a portion of a global risk budget `alpha_total`
according to a deterministic schedule. The verifier recomputes the expected
`alpha_i` for the current round and rejects any mismatch. Under the assumptions
of the sealed evaluation model and the chosen e-value construction, the total
false-accept probability across all time is bounded by `alpha_total`.

## Non-interference theorem (semantic)

Let `E_t` be the environment at time `t`, and `E_{t+1} = E_t ⊎ E_Δ` be a
definitional extension with fresh symbols. For any closed term `e` that refers
only to symbols in `E_t`,

```
eval(E_{t+1}, e) = eval(E_t, e)
```

This follows by structural induction on evaluation and the freshness constraint.
