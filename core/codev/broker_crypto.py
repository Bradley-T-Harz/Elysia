"""Narrow broker signatures compatible with browser WebCrypto P-256.

The signed payload is the exact UTF-8 JSON string carried by the envelope. Neither
peer needs to reproduce the other's JSON serialization. Keys are session-local;
this module creates no durable key files or native application credentials.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

from core.codev.contracts import BrokerProof, BrowserPublicKey


def encode64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode64(value: str, length: int) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("invalid_signature_encoding")
    decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if len(decoded) != length or encode64(decoded) != value:
        raise ValueError("noncanonical_signature_encoding")
    return decoded


def new_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def public_key(key: ec.EllipticCurvePrivateKey) -> BrowserPublicKey:
    numbers = key.public_key().public_numbers()
    return BrowserPublicKey(x=encode64(numbers.x.to_bytes(32, "big")),
                            y=encode64(numbers.y.to_bytes(32, "big")))


def load_public(value: BrowserPublicKey) -> ec.EllipticCurvePublicKey:
    # The crypto library also checks that the coordinates are on this curve.
    numbers = ec.EllipticCurvePublicNumbers(int.from_bytes(decode64(value.x, 32), "big"),
                                           int.from_bytes(decode64(value.y, 32), "big"), ec.SECP256R1())
    return numbers.public_key()


def sign(key: ec.EllipticCurvePrivateKey, message: bytes) -> str:
    r, s = decode_dss_signature(key.sign(message, ec.ECDSA(hashes.SHA256())))
    return encode64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def verify(key: BrowserPublicKey, message: bytes, signature: str) -> bool:
    try:
        raw = decode64(signature, 64)
        der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        load_public(key).verify(der, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (ValueError, InvalidSignature):
        return False


def _components(values: list[str]) -> bytes:
    if any(not value or any(char in value for char in "\r\n\0") for value in values):
        raise ValueError("invalid_broker_transcript")
    return "\n".join(values).encode("utf-8")


def request_message(origin: str, path: str, proof: BrokerProof, payload_json: str) -> bytes:
    return _components(["elysia-codev-request-1", origin, "POST", path, proof.pairing_id,
                        proof.browser_session_id, proof.online_account_id, proof.nonce,
                        str(proof.timestamp_ms), sha256(payload_json.encode("utf-8")).hexdigest()])


def response_message(origin: str, path: str, proof: BrokerProof, request_json: str, response_json: str) -> bytes:
    return _components(["elysia-codev-response-1", origin, path, proof.pairing_id,
                        proof.browser_session_id, proof.online_account_id, proof.nonce,
                        sha256(request_json.encode("utf-8")).hexdigest(),
                        sha256(response_json.encode("utf-8")).hexdigest()])


def strict_json(value: str) -> dict:
    def object_pairs(pairs):
        result = {}
        for key, child in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = child
        return result

    def invalid_constant(_value):
        raise ValueError("invalid_json_constant")

    result = json.loads(value, object_pairs_hook=object_pairs, parse_constant=invalid_constant)
    if not isinstance(result, dict):
        raise ValueError("broker_payload_must_be_object")
    return result
