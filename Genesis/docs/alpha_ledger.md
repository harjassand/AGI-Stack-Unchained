# AlphaLedger (Level-1)

AlphaLedger enforces global statistical validity across unbounded adaptive search. It is the sole authority for allocating false-admission risk within an epoch.

## Normative Default Summary (MUST implement)

- DeploymentGrade: alpha-spending with `alpha_i = alpha_total * (6/pi^2) * (1/i^2)`.
- ResearchGrade: LORD online FDR with the `gamma_j` schedule and wealth updates defined below.

## Normative Default (MUST implement)

## Extensions (MAY implement)

- Global e-process for DeploymentGrade.
- SAFFRON for ResearchGrade when e-values are available.

## Modes

- **DeploymentGrade (mandatory)**: controls family-wise error rate (FWER) using alpha-spending.
- **ResearchGrade (mandatory)**: controls online false discovery rate (FDR) using a conservative online FDR rule.

## State Variables (per epoch)

- `epoch_id`
- `alpha_total`: total FWER budget for DeploymentGrade.
- `alpha_spent`: cumulative alpha charged.
- `attempt_counter`: monotone integer for DeploymentGrade evaluation attempts.
- `fdr_target`: target FDR level for ResearchGrade.
- `fdr_wealth`: current alpha-investing wealth (non-negative).
- `research_attempt_counter`: monotone integer for ResearchGrade attempts.
- `ledger_entries[]`: append-only audit records (see Audit Logs).

## DeploymentGrade: Alpha-Spending (Normative)

### Allocation Schedule

For attempt index i = 1, 2, ... define:

```
alpha_i = alpha_total * (6 / pi^2) * (1 / i^2)
```

This ensures:

```
Sum_{i=1..infty} alpha_i <= alpha_total
```

### Admission Rule

- For attempt i, CDEL MUST use alpha_i to set the statistical decision threshold.
- Any acceptance MUST be a valid level-alpha_i test under the declared statistical_spec.
- The test MUST be time-uniform if the evaluation is adaptive or sequential.
- `attempt_counter` MUST increment for every DeploymentGrade evaluation attempt, PASS or FAIL.

### Charging Policy

- On **PASS**, charge exactly alpha_i from alpha_total.
- On **FAIL**, charge alpha_i or a smaller conservative amount. Charging MUST NOT be lower than the test's actual type-I error.

### Exhaustion

- If `alpha_spent + alpha_i > alpha_total`, CDEL MUST return FAIL without evaluation.

## ResearchGrade: Online FDR Control (Normative)

AlphaLedger MUST implement an online FDR rule. Standardize on **LORD** by default (SAFFRON MAY be used when e-values are available).

### LORD Parameters

- `gamma_j = (6 / pi^2) * (1 / j^2)` for j = 1, 2, ...
- `w0 = fdr_target / 2` (initial wealth)
- `reward = fdr_target / 2` (wealth added upon rejection)

### LORD Update Rules

For test j with outcome `R_j` in {0,1}:

```
alpha_j_raw = gamma_j * w0 + sum_{k=1..j-1} gamma_{j-k} * R_k * reward
alpha_j = min(alpha_j_raw, fdr_wealth)
fdr_wealth = fdr_wealth - alpha_j + R_j * reward
```

`research_attempt_counter` MUST increment for every ResearchGrade evaluation attempt, PASS or FAIL.

### Dependence Correction

If independence is not certified, CDEL MUST apply a BY-style correction:

```
alpha_j = alpha_j / c_j,  where c_j = sum_{k=1..j} 1/k
```

### Requirements

- `alpha_j` MUST be non-increasing in j absent rejections.
- The update rule MUST be fixed per epoch and declared in ledger configuration.
- All accepted ResearchGrade capsules MUST be tagged as non-deployment.

### Exhaustion

- If `fdr_wealth` is below the minimum allocatable amount, CDEL MUST return FAIL without evaluation.

## Ledger Entry Schema (Audit)

Each evaluation attempt appends an entry:

- `epoch_id`
- `attempt_id` (monotone, unique)
- `capsule_hash`
- `grade` (DeploymentGrade or ResearchGrade)
- `alpha_allocated`
- `alpha_charged`
- `decision` (PASS/FAIL)
- `timestamp`

Audit logs are internal and MUST NOT be exposed to Genesis.

## Invariants (Auditable)

- `alpha_spent` MUST be non-decreasing and MUST satisfy `alpha_spent <= alpha_total`.
- `attempt_counter` and `research_attempt_counter` MUST be strictly increasing.
- For DeploymentGrade, `sum(alpha_allocated)` over attempts MUST be <= `alpha_total`.

## Correctness Requirements

- Ledger updates MUST be atomic with respect to evaluation results.
- Ledger MUST be append-only and tamper-evident.
- The test applied MUST match the declared statistical_spec and decision_rule.
