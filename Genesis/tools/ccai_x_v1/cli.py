#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

if __package__ is None:
    TOOLS_DIR = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(TOOLS_DIR))
    from ccai_x_v1.canonical_json import assert_no_floats
    from ccai_x_v1.hashes import (
        candidate_id_from_tar,
        do_payload_hash,
        intervention_log_link_hash,
        mechanism_hash,
    )
    from ccai_x_v1.validate_instance import load_json_strict, validate_path
else:
    from .canonical_json import assert_no_floats
    from .hashes import (
        candidate_id_from_tar,
        do_payload_hash,
        intervention_log_link_hash,
        mechanism_hash,
    )
    from .validate_instance import load_json_strict, validate_path

ZERO_HASH = "0" * 64


def _load_json_file(path: Path):
    text = path.read_text(encoding="utf-8")
    obj = load_json_strict(text)
    assert_no_floats(obj)
    return obj


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        validate_path(Path(args.json_path))
    except Exception as exc:
        print(f"validation failed: {exc}")
        return 1
    print("validation OK")
    return 0


def _cmd_do_payload_hash(args: argparse.Namespace) -> int:
    try:
        obj = _load_json_file(Path(args.json_path))
        print(do_payload_hash(obj))
        return 0
    except Exception as exc:
        print(f"do-payload-hash failed: {exc}")
        return 1


def _cmd_mechanism_hash(args: argparse.Namespace) -> int:
    try:
        obj = _load_json_file(Path(args.json_path))
        print(mechanism_hash(obj))
        return 0
    except Exception as exc:
        print(f"mechanism-hash failed: {exc}")
        return 1


def _cmd_candidate_id(args: argparse.Namespace) -> int:
    try:
        print(candidate_id_from_tar(args.tar))
        return 0
    except Exception as exc:
        print(f"candidate-id failed: {exc}")
        return 1


def _cmd_log_chainhash(args: argparse.Namespace) -> int:
    path = Path(args.jsonl_path)
    try:
        raw = path.read_bytes()
        if not raw.endswith(b"\n"):
            raise ValueError("JSONL file must end with LF")
        lines = raw.split(b"\n")
        prev = ZERO_HASH
        for idx, line in enumerate(lines[:-1]):
            if not line:
                raise ValueError(f"empty line at {idx}")
            obj = load_json_strict(line.decode("utf-8"))
            assert_no_floats(obj)
            if obj.get("prev_link_hash") != prev:
                raise ValueError(f"prev_link_hash mismatch at line {idx}")
            computed = intervention_log_link_hash(prev, obj)
            if obj.get("link_hash") != computed:
                raise ValueError(f"link_hash mismatch at line {idx}")
            prev = computed
        if args.expect_last and prev != args.expect_last:
            raise ValueError("final link hash mismatch")
        print(prev)
        return 0
    except Exception as exc:
        print(f"log-chainhash failed: {exc}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="ccai-x", description="CCAI-X v1 validation and hashing tools")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate JSON/JSONL instance")
    validate.add_argument("json_path")
    validate.set_defaults(func=_cmd_validate)

    do_payload = sub.add_parser("do-payload-hash", help="compute do_payload hash")
    do_payload.add_argument("json_path")
    do_payload.set_defaults(func=_cmd_do_payload_hash)

    mech = sub.add_parser("mechanism-hash", help="compute mechanism hash")
    mech.add_argument("json_path")
    mech.set_defaults(func=_cmd_mechanism_hash)

    cand = sub.add_parser("candidate-id", help="compute candidate_id from tar")
    cand.add_argument("--tar", required=True)
    cand.set_defaults(func=_cmd_candidate_id)

    log = sub.add_parser("log-chainhash", help="compute final intervention log link hash")
    log.add_argument("jsonl_path")
    log.add_argument("--expect-last")
    log.set_defaults(func=_cmd_log_chainhash)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
