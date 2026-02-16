# Shadow-CDEL Rules (ALGORITHM only)

## One-Sided Screening Rule

For a metric in [0,1], compute a Hoeffding lower confidence bound (LCB):

```
LCB = value - sqrt(log(1/delta) / (2n))
```

Shadow PASS iff `LCB >= target + margin` for `direction == maximize`.
For `direction == minimize`, use UCB:

```
UCB = value + sqrt(log(1/delta) / (2n))
```

Shadow PASS iff `UCB <= target - margin`.

The margin starts at a conservative default and increases (bounded) only when a
Shadow PASS leads to a promoted FAIL.

## Forager Tests (Bounded)

When baseline tests pass, Shadow-CDEL generates a bounded set of additional tests
from a finite template family. Any forager failure yields Shadow FAIL and emits
a counterexample trace. The generation is deterministic given the seed and
counterexample set.

## Worked Example

- metric value: 0.75
- n = 100
- delta = 0.01
- target = 0.70
- margin = 0.05

Radius:

```
rad = sqrt(log(100) / 200) ≈ 0.1516
LCB = 0.75 - 0.1516 = 0.5984
```

Decision: FAIL because `LCB < 0.75` (target + margin).
