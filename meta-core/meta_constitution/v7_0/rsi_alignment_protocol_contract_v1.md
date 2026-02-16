# RSI Alignment Protocol Contract v1 (Superego Protocol v1)

This contract defines the mandatory alignment and superego enforcement rules for v7.0.

## CA-CONST-POLICY-0
The superego policy hash MUST match the policy lock. Any mismatch is fatal and must halt action execution.

## CA-CONST-DECISION-0
Every executed action MUST have a preceding ALLOW superego decision bound to the correct policy hash.

## CA-CONST-NET-0
`NETWORK_ANY` capability is forbidden for all objective classes.

## CA-CONST-BOUNDLESS-0
Boundless research actions require a valid clearance receipt AND the operator `ENABLE_RESEARCH` control signal.

## CA-CONST-DRIFT-0
Policy drift or meta drift MUST cause the daemon to pause and refuse actions.

## CA-CONST-LOG-0
The superego ledger is append-only and hash-chained. Missing or malformed entries are invalid.
