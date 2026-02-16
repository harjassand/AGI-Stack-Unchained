#!/usr/bin/env python3
import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict

try:
    from jsonschema import Draft202012Validator
except Exception as exc:
    print(f"jsonschema not available: {exc}", file=sys.stderr)
    sys.exit(2)

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parents[0]

sys.path.insert(0, str(TOOLS_DIR))
import canonicalize as canon  # noqa: E402

CAPSULE_SCHEMA_PATH = ROOT / "schema" / "capsule.schema.json"
RECEIPT_SCHEMA_PATH = ROOT / "schema" / "receipt.schema.json"

PASS_CAPSULE_ID = "00000000-0000-0000-0000-000000000001"

RECEIPT_TEMPLATE = {
    "schema_version": "1.0.1",
    "receipt_version": "1.0.1",
    "canonicalization": "gcj-1",
    "receipt_id": "00000000-0000-0000-0000-0000000000aa",
    "epoch_id": "",
    "capsule_hash": "",
    "budgets_spent": {
        "alpha_spent": "0",
        "privacy_spent": {"epsilon_spent": "0", "delta_spent": "0"},
        "compute_spent": {"compute_units": 0, "wall_time_ms": 0, "adversary_strength_used": 0},
    },
    "rng_commitment_id": "rng-commit-0",
    "measurement_transcript_hash": "1" * 64,
    "admission_token": "admission-token-0",
    "signature": {"alg": "ed25519", "key_id": "mock-key-1", "signature_base64": "AA=="},
}


def load_schema(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def parse_json(text: str) -> Dict[str, Any]:
    return json.loads(text)


def validate_capsule(capsule: Dict[str, Any]) -> bool:
    schema = load_schema(CAPSULE_SCHEMA_PATH)
    validator = Draft202012Validator(schema)
    return not any(validator.iter_errors(capsule))


def validate_receipt(receipt: Dict[str, Any]) -> bool:
    schema = load_schema(RECEIPT_SCHEMA_PATH)
    validator = Draft202012Validator(schema)
    return not any(validator.iter_errors(receipt))


def bid_matches_capsule(bid: Dict[str, Any], capsule: Dict[str, Any]) -> bool:
    return bid == capsule.get("budget_bid")


def build_receipt(capsule: Dict[str, Any], epoch_id: str) -> Dict[str, Any]:
    receipt = json.loads(json.dumps(RECEIPT_TEMPLATE))
    receipt["epoch_id"] = epoch_id
    capsule_for_hash = json.loads(json.dumps(capsule), parse_float=Decimal, parse_int=Decimal)
    receipt["capsule_hash"] = canon.compute_capsule_hash(capsule_for_hash)
    if not validate_receipt(receipt):
        raise ValueError("receipt schema validation failed")
    return receipt


def evaluate_request(request_obj: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(request_obj, dict):
        raise ValueError("request must be a JSON object")

    if "epoch_id" not in request_obj or "capsule" not in request_obj or "bid" not in request_obj:
        raise ValueError("missing required fields")

    epoch_id = request_obj["epoch_id"]
    capsule = request_obj["capsule"]
    bid = request_obj["bid"]

    if isinstance(capsule, dict) and capsule.get("ref_type"):
        return {"result": "FAIL"}

    if not isinstance(capsule, dict) or not isinstance(bid, dict):
        raise ValueError("capsule and bid must be objects")

    if not validate_capsule(capsule):
        return {"result": "FAIL"}

    if not bid_matches_capsule(bid, capsule):
        return {"result": "FAIL"}

    if capsule.get("capsule_id") != PASS_CAPSULE_ID:
        return {"result": "FAIL"}

    receipt = build_receipt(capsule, epoch_id)
    return {"result": "PASS", "receipt": receipt}


def run_stdin() -> int:
    payload = sys.stdin.read()
    try:
        request_obj = parse_json(payload)
        response = evaluate_request(request_obj)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(json.dumps(response))
    return 0


def run_http(host: str, port: int) -> int:
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path not in {"/evaluate/v1", "/evaluate"}:
                self.send_response(404)
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            try:
                request_obj = parse_json(body)
                response = evaluate_request(request_obj)
                response_bytes = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_bytes)))
                self.end_headers()
                self.wfile.write(response_bytes)
            except Exception:
                self.send_response(400)
                self.end_headers()

        def log_message(self, _format: str, *args) -> None:
            return

    server = HTTPServer((host, port), Handler)
    server.serve_forever()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Mock CDEL Evaluate endpoint")
    parser.add_argument("--mode", choices=["stdin", "http"], default="stdin")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    if args.mode == "stdin":
        return run_stdin()

    return run_http(args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
