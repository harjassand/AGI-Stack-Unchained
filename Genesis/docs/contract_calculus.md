# Probabilistic Contract Calculus (Level-1)

This document defines how probabilistic guarantees compose and how dependencies are tracked.

## Guarantee Object

A probabilistic guarantee MUST be represented explicitly:

- `statement`: the claim (e.g., coverage >= 1 - alpha)
- `delta`: failure probability
- `dependencies`: identifiers for shared randomness, data, or evaluators
- `uncertainty_object`: representation of uncertainty (e.g., conformal set, PAC-Bayes bound)

## Dependency Graph

- Each capsule maintains a dependency graph with nodes for datasets, randomness sources, and evaluator components.
- Edges indicate shared dependence. Acyclicity is not required but cycles MUST be recorded.

### Dependency Tags

- `data:<dataset_id>`
- `rng:<seed_scope>`
- `evaluator:<component_id>`
- `artifact:<capsule_hash>`

## Composition Rules (Normative)

### Sequential Composition

If A then B are executed sequentially with possible dependence:

```
(delta_total) <= delta_A + delta_B
```

This union bound is the default unless independence is certified.

### Parallel Composition

If A and B are independent (as certified by disjoint dependency tags):

```
(delta_total) = 1 - (1 - delta_A)(1 - delta_B)
```

Otherwise use the union bound.

### Conditional Guarantees

If B depends on A's outcome (adaptive):

- Use time-uniform or anytime-valid methods for B.
- Aggregate via union bound unless the dependence is explicitly modeled.

## Independence Certification

- Independence MUST be certified by a checker (certificate in evidence).
- Absent a certificate, independence is not assumed.

## Contract Combination Operators

- `AND`: combine guarantees using union bound unless independent.
- `OR`: conservative bound using max(delta_i) for disjoint events, otherwise union bound.
- `IMPLIES`: treated as conditional with explicit delta tracking.

## Default Conservative Rule

When in doubt, propagate failure probabilities via union bound and mark dependencies as shared.

## Uncertainty Object Propagation

- If guarantees depend on uncertainty sets, the composed uncertainty set MUST be the intersection when both must hold (AND) and the union when either may hold (OR).
- For conformal or PAC-Bayes objects, composition MUST retain the tightest bound consistent with the union-bound delta accounting.
- If uncertainty objects are incompatible (different data scopes or metrics), composition MUST FAIL.
