"""
AP2 SDK-equivalent crypto wrapper (Sprint 1 stub).

Per 0503 briefing correction:
> "AP2 SDK는 단순 암호학적 작업"
We expose only sign/verify here. Business logic (constraint eval, accumulators)
lives in policy_server / facilitator. Swapping for the real Python AP2 SDK
should be a one-class change.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


@dataclass
class Keypair:
    private: Ed25519PrivateKey
    public: Ed25519PublicKey

    @classmethod
    def generate(cls) -> "Keypair":
        priv = Ed25519PrivateKey.generate()
        return cls(private=priv, public=priv.public_key())

    def public_bytes(self) -> bytes:
        from cryptography.hazmat.primitives import serialization

        return self.public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )


class MandateClient:
    """JWS-like compact serialization (header.payload.signature, ed25519)."""

    HEADER = {"alg": "EdDSA", "typ": "AP2-Mandate+JWT"}

    @classmethod
    def sign(cls, payload: dict, kp: Keypair) -> str:
        header_b64 = _b64url(json.dumps(cls.HEADER, separators=(",", ":")).encode())
        payload_b64 = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        signing_input = f"{header_b64}.{payload_b64}".encode()
        sig = kp.private.sign(signing_input)
        return f"{header_b64}.{payload_b64}.{_b64url(sig)}"

    @classmethod
    def verify(cls, jwt: str, pubkey: Ed25519PublicKey) -> dict:
        try:
            header_b64, payload_b64, sig_b64 = jwt.split(".")
        except ValueError as e:
            raise InvalidMandateSignature("malformed_jwt") from e
        signing_input = f"{header_b64}.{payload_b64}".encode()
        try:
            pubkey.verify(_b64url_decode(sig_b64), signing_input)
        except Exception as e:
            raise InvalidMandateSignature("signature_verify_failed") from e
        return json.loads(_b64url_decode(payload_b64))

    @classmethod
    def peek(cls, jwt: str) -> dict:
        """Decode payload without verifying (debug only)."""
        _, payload_b64, _ = jwt.split(".")
        return json.loads(_b64url_decode(payload_b64))


class InvalidMandateSignature(Exception):
    pass


class ReceiptClient:
    """Receipt = same JWS shape, signed by Facilitator key."""

    HEADER = {"alg": "EdDSA", "typ": "AP2-Receipt+JWT"}

    @classmethod
    def create(cls, payload: dict, kp: Keypair) -> str:
        header_b64 = _b64url(json.dumps(cls.HEADER, separators=(",", ":")).encode())
        payload_b64 = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        signing_input = f"{header_b64}.{payload_b64}".encode()
        sig = kp.private.sign(signing_input)
        return f"{header_b64}.{payload_b64}.{_b64url(sig)}"

    @classmethod
    def verify(cls, jwt: str, pubkey: Ed25519PublicKey) -> dict:
        return MandateClient.verify(jwt, pubkey)
