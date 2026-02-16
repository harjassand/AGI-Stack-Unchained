#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib import request as urlrequest

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def send_http(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlrequest.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_subprocess(cmd: str, payload: dict) -> dict:
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="ignore"))
    return json.loads(proc.stdout.decode("utf-8"))


def send_file(ipc_dir: Path, payload: dict, timeout_seconds: float) -> dict:
    requests_dir = ipc_dir / "requests"
    responses_dir = ipc_dir / "responses"
    requests_dir.mkdir(parents=True, exist_ok=True)
    responses_dir.mkdir(parents=True, exist_ok=True)
    req_id = uuid.uuid4().hex
    req_path = requests_dir / f"{req_id}.json"
    resp_path = responses_dir / f"{req_id}.json"
    req_path.write_text(json.dumps(payload), encoding="utf-8")

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if resp_path.exists():
            return load_json(resp_path)
        time.sleep(0.1)
    raise TimeoutError(f"no response file at {resp_path}")


def validate_response_shape(response: dict) -> None:
    if not isinstance(response, dict):
        raise AssertionError("response must be a JSON object")
    result = response.get("result")
    if result not in {"PASS", "FAIL"}:
        raise AssertionError("result must be PASS or FAIL")
    allowed_keys = {"result", "receipt"}
    extra_keys = set(response.keys()) - allowed_keys
    if extra_keys:
        raise AssertionError(f"response has unexpected fields: {sorted(extra_keys)}")
    if result == "PASS":
        if "receipt" not in response or not isinstance(response["receipt"], dict):
            raise AssertionError("receipt must be present on PASS")
    if result == "FAIL" and "receipt" in response:
        raise AssertionError("receipt must be absent on FAIL")


def verify_receipt(capsule_path: Path, receipt_obj: dict) -> None:
    tmp_path = ROOT / "dist" / "_tmp_receipt.json"
    tmp_path.write_text(json.dumps(receipt_obj), encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "verify_receipt.py"), str(tmp_path), str(capsule_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0:
            raise AssertionError(proc.stderr.decode("utf-8", errors="ignore"))
    finally:
        tmp_path.unlink(missing_ok=True)


def run_ledger_sims() -> None:
    for script in (
        ROOT / "ledger_sim" / "alpha_ledger_sim.py",
        ROOT / "ledger_sim" / "privacy_ledger_sim.py",
        ROOT / "ledger_sim" / "compute_ledger_sim.py",
    ):
        proc = subprocess.run([sys.executable, str(script)], check=False)
        if proc.returncode != 0:
            raise AssertionError(f"ledger sim failed: {script}")


def main() -> int:
    parser = argparse.ArgumentParser(description="CDEL conformance harness")
    parser.add_argument("--mode", choices=["http", "subprocess", "file"], required=True)
    parser.add_argument("--http-url")
    parser.add_argument("--subprocess-cmd")
    parser.add_argument("--ipc-dir")
    parser.add_argument("--catalog", default="conformance/tests/catalog.json")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--skip-pass-required", action="store_true")
    args = parser.parse_args()

    if args.mode == "http" and not args.http_url:
        parser.error("--http-url is required for http mode")
    if args.mode == "subprocess" and not args.subprocess_cmd:
        parser.error("--subprocess-cmd is required for subprocess mode")
    if args.mode == "file" and not args.ipc_dir:
        parser.error("--ipc-dir is required for file mode")

    catalog_path = resolve_path(args.catalog)
    catalog = load_json(catalog_path)
    tests = catalog.get("tests", [])
    if not tests:
        raise AssertionError("no tests found in catalog")

    failures = []
    for test in tests:
        name = test.get("name", "<unnamed>")
        test_type = test.get("type", "evaluate")

        if test_type == "ledger_sim":
            try:
                run_ledger_sims()
            except Exception as exc:
                failures.append(f"{name}: {exc}")
            continue

        if test.get("requires_pass") and args.skip_pass_required:
            continue

        capsule_path = resolve_path(test["capsule_path"])
        capsule = load_json(capsule_path)
        bid = test.get("bid_override") or capsule.get("budget_bid")
        if bid is None:
            failures.append(f"{name}: missing bid and capsule has no budget_bid")
            continue

        request_obj = {
            "epoch_id": test.get("epoch_id", "epoch-1"),
            "capsule": capsule,
            "bid": bid,
        }

        try:
            if args.mode == "http":
                response = send_http(args.http_url, request_obj)
            elif args.mode == "subprocess":
                response = send_subprocess(args.subprocess_cmd, request_obj)
            else:
                response = send_file(Path(args.ipc_dir), request_obj, args.timeout_seconds)
            validate_response_shape(response)
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            continue

        expected = test.get("expect_result")
        if expected and response.get("result") != expected:
            failures.append(f"{name}: expected {expected}, got {response.get('result')}")
            continue

        if response.get("result") == "PASS" and test.get("verify_receipt"):
            try:
                verify_receipt(capsule_path, response["receipt"])
            except Exception as exc:
                failures.append(f"{name}: receipt verification failed: {exc}")

    if failures:
        for failure in failures:
            print(failure)
        return 1

    print("conformance harness OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
