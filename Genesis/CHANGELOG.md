# Changelog

All notable changes to the Level-1 spec pack are documented here.

## [1.0.1] - 2026-01-23

### Breaking

- Budget money-like quantities are now canonical decimal strings (not JSON numbers) in capsules and receipts; schema versions updated to 1.0.1.

### Changed

- GCJ-1 canonicalization clarifies money-like fields and numeric stability.
- Canonicalization test vectors updated to include decimal-string budgets.

## [1.0.0] - 2025-01-01

### Added

- Level-1 capsule schema and examples.
- CDEL Evaluate protocol and PASS receipt specification.
- AlphaLedger, PrivacyLedger, and ComputeLedger specs with invariants.
- Contract taxonomy, probabilistic contract calculus, robustness, assumptions, determinism, and TCB specs.
- Canonicalization spec, test vectors, and hashing tool.
- Receipt schema and verification tool.
- Ledger simulators and CI checks.
- Phase-2 spec starters: Shadow-CDEL, Genesis interfaces, promotion policy, experiment capsules.
