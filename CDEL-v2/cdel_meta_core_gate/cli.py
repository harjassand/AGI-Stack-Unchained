from __future__ import annotations

import argparse
import json
import sys

from .errors import MetaCoreGateInternal, MetaCoreGateInvalid
from .runner import audit_meta_core_active


def _audit_payload(audit) -> dict:
    return {
        "verdict": "OK",
        "active_bundle_hash": audit.active_bundle_hash,
        "prev_active_bundle_hash": audit.prev_active_bundle_hash,
        "kernel_hash": audit.kernel_hash,
        "meta_hash": audit.meta_hash,
        "ruleset_hash": audit.ruleset_hash,
        "toolchain_merkle_root": audit.toolchain_merkle_root,
        "ledger_head_hash": audit.ledger_head_hash,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="cdel-meta-core-gate")
    sub = parser.add_subparsers(dest="cmd", required=True)

    audit_p = sub.add_parser("audit_active")
    audit_p.add_argument("--meta-core-root", required=True)

    args = parser.parse_args()

    if args.cmd == "audit_active":
        try:
            audit = audit_meta_core_active(args.meta_core_root)
        except MetaCoreGateInvalid:
            raise SystemExit(2)
        except MetaCoreGateInternal:
            raise SystemExit(1)
        payload = _audit_payload(audit)
        print(json.dumps(payload, sort_keys=True))
        return

    raise SystemExit(1)


if __name__ == "__main__":
    main()
