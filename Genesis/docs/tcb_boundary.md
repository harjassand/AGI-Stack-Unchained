# TCB Boundary and Certificate Discipline (Level-1)

This document defines the minimal trusted computing base (TCB) and how untrusted tools must provide checkable artifacts.

## Trusted Components (Normative)

Trusted kernel MUST include:

- Capsule parser and schema checker
- IR type/effect checker
- Certificate checker
- AlphaLedger
- PrivacyLedger
- ComputeLedger
- Sandbox runtime + measurement harness

## Untrusted Components (Allowed)

Untrusted tools MAY include:

- SMT solvers
- Theorem provers
- Fuzzers
- Slice miners
- Adversarial scenario generators

Untrusted tools MUST NOT return a boolean result as final authority. They must output certificates or transcripts that the trusted kernel can verify.

## Certificate Formats

Each certificate MUST include:

- `cert_type`
- `payload_hash`
- `checker_id`
- Optional: `proof_format`, `tool_version`, `transcript_hash`

The trusted kernel MUST validate the certificate using a fixed checker identified by `checker_id`.

## LCF-Style Discipline

- The kernel is the only entity that can produce PASS/FAIL.
- All external reasoning is reduced to checkable proof objects.
- Checker implementations MUST be small, versioned, and auditable.
