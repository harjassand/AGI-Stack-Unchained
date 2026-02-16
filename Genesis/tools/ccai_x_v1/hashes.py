import hashlib
import tarfile
from copy import deepcopy

from .canonical_json import assert_no_floats, to_gcj1_bytes
from .validate_instance import load_json_strict

ZERO_HASH = "0" * 64
CANDIDATE_DOMAIN_SEP = b"ccai_x_mind_patch_candidate_v1\n"
REQUIRED_TAR_ENTRIES = {
    "manifest.json": "manifest",
    "mechanism_registry.json": "mechanism_registry",
    "policy_prior.json": "policy_prior",
    "preference_capsule.json": "preference_capsule",
    "inference_kernel_isa.json": "inference_kernel_isa",
    "markov_blanket_spec.json": "markov_blanket_spec",
    "do_map.json": "do_map",
}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_raw(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _ensure_hex_len(value: str, name: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{name} must be 64 hex chars")


def do_payload_hash(do_payload_obj) -> str:
    return sha256_hex(to_gcj1_bytes(do_payload_obj))


def mechanism_hash(mechanism_obj) -> str:
    return sha256_hex(to_gcj1_bytes(mechanism_obj))


def workspace_state_hash(prev_hash_hex: str, beliefs_obj) -> str:
    _ensure_hex_len(prev_hash_hex, "prev_state_hash")
    prev_bytes = bytes.fromhex(prev_hash_hex)
    beliefs_hash = _sha256_raw(to_gcj1_bytes(beliefs_obj))
    return sha256_hex(prev_bytes + beliefs_hash)


def intervention_log_link_hash(prev_link_hash_hex: str, entry_obj_without_link_hash) -> str:
    _ensure_hex_len(prev_link_hash_hex, "prev_link_hash")
    entry_obj = deepcopy(entry_obj_without_link_hash)
    entry_obj["link_hash"] = ZERO_HASH
    prev_bytes = bytes.fromhex(prev_link_hash_hex)
    payload = to_gcj1_bytes(entry_obj)
    return sha256_hex(prev_bytes + payload)


def _ensure_hex(value: str, name: str) -> None:
    _ensure_hex_len(value, name)
    if value != value.lower():
        raise ValueError(f"{name} must be lowercase hex")
    try:
        bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be lowercase hex") from exc


def _parse_manifest(manifest_bytes: bytes) -> dict:
    text = manifest_bytes.decode("utf-8")
    manifest_obj = load_json_strict(text)
    assert_no_floats(manifest_obj)
    if not isinstance(manifest_obj, dict):
        raise ValueError("manifest must be a JSON object")
    candidate_id = manifest_obj.get("candidate_id")
    if not isinstance(candidate_id, str):
        raise ValueError("manifest candidate_id must be a string")
    _ensure_hex(candidate_id, "candidate_id")
    return manifest_obj


def _manifest_zeroed_bytes(manifest_obj: dict) -> bytes:
    manifest_zeroed = deepcopy(manifest_obj)
    manifest_zeroed["candidate_id"] = ZERO_HASH
    return to_gcj1_bytes(manifest_zeroed)


def candidate_id_from_components(manifest_obj: dict, blobs: dict) -> str:
    m = _sha256_raw(_manifest_zeroed_bytes(manifest_obj))
    r = _sha256_raw(blobs["mechanism_registry.json"])
    p = _sha256_raw(blobs["policy_prior.json"])
    pref = _sha256_raw(blobs["preference_capsule.json"])
    isa = _sha256_raw(blobs["inference_kernel_isa.json"])
    blanket = _sha256_raw(blobs["markov_blanket_spec.json"])
    d = _sha256_raw(blobs["do_map.json"])
    return sha256_hex(CANDIDATE_DOMAIN_SEP + m + r + p + pref + isa + blanket + d)


def candidate_id_from_tar(tar_path: str) -> str:
    tar_path = str(tar_path)
    blobs = {}
    with tarfile.open(tar_path, "r") as tar:
        members = {member.name: member for member in tar.getmembers()}
        missing = [name for name in REQUIRED_TAR_ENTRIES if name not in members]
        if missing:
            raise ValueError(f"tar missing required entries: {missing}")
        for name in REQUIRED_TAR_ENTRIES:
            member = members[name]
            if not member.isfile():
                raise ValueError(f"tar entry not a file: {name}")
            fp = tar.extractfile(member)
            if fp is None:
                raise ValueError(f"unable to read tar entry: {name}")
            blobs[name] = fp.read()

    manifest_obj = _parse_manifest(blobs["manifest.json"])
    candidate_id = candidate_id_from_components(manifest_obj, blobs)
    if manifest_obj.get("candidate_id") != candidate_id:
        raise ValueError("manifest candidate_id does not match computed candidate_id")
    return candidate_id
