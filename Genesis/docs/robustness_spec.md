# RobustnessSpec (Level-1)

RobustnessSpec defines admissible worst-case guarantees. Only certified capacity-bounded slice families or approved DRO sets are allowed.

## Normative Default Summary (MUST implement)

- Certified slice families (`certified_slices`) with bounded capacity parameters.

## Normative Default (MUST implement)

## Extensions (MAY implement)

- DRO uncertainty sets (`dro`) as defined below.

## Modes

- `certified_slices`: worst-slice risk over a certified slice class.
- `dro`: worst-case risk over a declared uncertainty set.

## Certified Slice Families (Normative)

Allowed slice families (`S_cert`) include:

- Decision trees with bounded depth and audited features.
- Monotone k-conjunctions over audited features.
- Linear thresholds over fixed feature sets.
- Finite template families with bounded cardinality.

### Parameters

- `family`: one of the allowed families.
- `capacity.parameters`: explicit capacity bounds (e.g., depth, k, feature count).

### Discovery vs Certification Split

- **Mining Split (A)**: used by untrusted miners to propose worst slices.
- **Certification Split (B)**: used by CDEL to certify worst-slice risk.
- Certification MUST use a correction for adaptivity (e.g., holdout correction or DP).
- Rotating splits is allowed but MUST be consistent with PrivacyLedger accounting.

### Acceptance Rule

- CDEL computes the worst-case risk over `S_cert` on split B.
- The capsule passes the robustness clause if worst-case risk <= `risk_bound`.

## DRO Sets (Normative)

Allowed uncertainty sets (`U`) include:

- f-divergence balls
- Wasserstein balls
- Bounded covariate-shift sets

### Parameters

- `class`: one of the allowed classes.
- `radius`: non-negative scalar.

### Acceptance Rule

- CDEL computes the worst-case risk over `U`.
- The capsule passes the robustness clause if worst-case risk <= `risk_bound`.

## Risk Metric

- The `risk_metric` must be one of the declared StatisticalSpec metrics.
- The `risk_bound` must be a scalar threshold.

## Rejection Conditions

- Any robustness clause referencing an unapproved slice family or DRO class is invalid and MUST be rejected.
- Any clause missing capacity parameters is invalid and MUST be rejected.
