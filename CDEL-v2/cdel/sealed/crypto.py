"""Signature utilities for sealed certificates."""

from __future__ import annotations

import base64
import binascii

from blake3 import blake3

try:  # pragma: no cover - optional dependency in some environments
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    _CRYPTO_AVAILABLE = True
except Exception:  # pragma: no cover - allow import without cryptography
    InvalidSignature = Exception
    serialization = None
    ed25519 = None
    _CRYPTO_AVAILABLE = False


SUPPORTED_SCHEMES = {"ed25519"}


def generate_keypair() -> tuple[str, str]:
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography is required for key generation")
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b64encode(private_bytes), _b64encode(public_bytes)


def generate_keypair_from_seed(seed: bytes) -> tuple[str, str]:
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography is required for key generation")
    seed_bytes = blake3(seed).digest()
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed_bytes)
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b64encode(private_bytes), _b64encode(public_bytes)


def sign_bytes(private_key_b64: str, payload: bytes) -> str:
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography is required for signing")
    private_bytes = _b64decode(private_key_b64)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
    signature = private_key.sign(payload)
    return _b64encode(signature)


def verify_signature(public_key_b64: str, payload: bytes, signature_b64: str, scheme: str) -> bool:
    if scheme not in SUPPORTED_SCHEMES:
        return False
    if not _CRYPTO_AVAILABLE:
        return False
    try:
        public_bytes = _b64decode(public_key_b64)
        signature = _b64decode(signature_b64)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_bytes)
        public_key.verify(signature, payload)
    except (InvalidSignature, ValueError, binascii.Error):
        return False
    return True


def public_key_from_private(private_key_b64: str) -> str:
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography is required for public key derivation")
    private_bytes = _b64decode(private_key_b64)
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b64encode(public_bytes)


def key_id_from_public_key(public_key_b64: str) -> str:
    public_bytes = _b64decode(public_key_b64)
    digest = blake3(public_bytes).hexdigest()
    return digest[:16]


def crypto_available() -> bool:
    return _CRYPTO_AVAILABLE


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"), validate=True)
