# RSI Boundless Math Protocol Contract v1

This contract defines mandatory constraints for v8.0 boundless math research.

## Clauses

- **BRM-CONST-OFFLINE-0**: All boundless math actions require `NETWORK_NONE`; any other network capability is forbidden and must be treated as fatal.
- **BRM-CONST-TOOLCHAIN-0**: A pinned math toolchain manifest is required; any toolchain hash mismatch is fatal.
- **BRM-CONST-2KEY-0**: Boundless math requires BOTH operator controls: `ENABLE_RESEARCH` and `ENABLE_BOUNDLESS_MATH`.
- **BRM-CONST-ACCEPT-0**: `PROOF_ACCEPTED` is valid only when a sealed PASS receipt exists that binds the toolchain and proof artifact hash.
- **BRM-CONST-NO-KERNEL-MOD-0**: Any attempt to modify proof checker/toolchain artifacts is denied.
- **BRM-CONST-RATE-0**: Per-tick attempt ceilings and daily budgets are mandatory; overruns must pause with `BUDGET_EXCEEDED`.
