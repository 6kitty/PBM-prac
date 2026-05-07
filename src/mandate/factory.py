"""
Open / Closed Mandate factories.

Open Mandate: long-running delegation, agent autonomously executes multiple
payments under constraints.
Closed Mandate (baseline): single-tx authorization, merchant_id and amount
fixed at signing time.
"""
from __future__ import annotations

import secrets
import time
import uuid
from typing import Literal

from pydantic import BaseModel

from constraints.schema import Constraint


class MandateScope(BaseModel):
    purpose: str
    campaign_id: str | None = None


class OpenMandatePayload(BaseModel):
    mandate_id: str
    issuer: str
    subject: str
    type: Literal["open"] = "open"
    scope: MandateScope
    constraints: list[Constraint]
    valid_from: int
    valid_until: int
    nonce: str
    iat: int


class ClosedMandatePayload(BaseModel):
    mandate_id: str
    issuer: str
    subject: str
    type: Literal["closed"] = "closed"
    scope: MandateScope
    constraints: list[Constraint]
    # Cart-bound fields (single transaction):
    merchant_id: str
    amount_usdc: float
    cart_id: str
    valid_from: int
    valid_until: int
    nonce: str
    iat: int


def _now() -> int:
    return int(time.time())


def _new_mandate_id() -> str:
    return "mnd_" + uuid.uuid4().hex


def _new_nonce() -> str:
    return "0x" + secrets.token_hex(16)


def build_open_mandate(
    issuer: str,
    subject: str,
    scope: MandateScope,
    constraints: list[Constraint],
    valid_seconds: int = 14 * 24 * 3600,
) -> OpenMandatePayload:
    now = _now()
    return OpenMandatePayload(
        mandate_id=_new_mandate_id(),
        issuer=issuer,
        subject=subject,
        scope=scope,
        constraints=constraints,
        valid_from=now,
        valid_until=now + valid_seconds,
        nonce=_new_nonce(),
        iat=now,
    )


def build_closed_mandate(
    issuer: str,
    subject: str,
    scope: MandateScope,
    constraints: list[Constraint],
    merchant_id: str,
    amount_usdc: float,
    cart_id: str,
    valid_seconds: int = 600,
) -> ClosedMandatePayload:
    now = _now()
    return ClosedMandatePayload(
        mandate_id=_new_mandate_id(),
        issuer=issuer,
        subject=subject,
        scope=scope,
        constraints=constraints,
        merchant_id=merchant_id,
        amount_usdc=amount_usdc,
        cart_id=cart_id,
        valid_from=now,
        valid_until=now + valid_seconds,
        nonce=_new_nonce(),
        iat=now,
    )
