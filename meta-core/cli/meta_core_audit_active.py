#!/usr/bin/env python3
import argparse
import os
import sys

ENGINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "engine"))
sys.path.insert(0, ENGINE_DIR)

import gcj1_min  # noqa: E402
from audit import audit_active  # noqa: E402
from errors import InternalError  # noqa: E402
from atomic_fs import atomic_write_text  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--meta-core-root", required=True)
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args()

    try:
        exit_code, out_dict = audit_active(args.meta_core_root)
    except InternalError:
        exit_code = 1
        out_dict = _internal_audit_dict()
    except Exception:  # noqa: BLE001
        exit_code = 1
        out_dict = _internal_audit_dict()

    out_text = gcj1_min.dumps(out_dict) + "\n"
    atomic_write_text(args.out_json, out_text)
    sys.stdout.write(out_text)
    return exit_code


def _internal_audit_dict() -> dict:
    return {
        "verdict": "INTERNAL_ERROR",
        "active_bundle_hash": "",
        "prev_active_bundle_hash": "",
        "kernel_hash": "",
        "meta_hash": "",
        "ruleset_hash": "",
        "toolchain_merkle_root": "",
        "ledger_head_hash": "",
    }


if __name__ == "__main__":
    raise SystemExit(main())
