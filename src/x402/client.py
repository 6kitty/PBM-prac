"""
Agent-side x402 client.

PRE Constraint self-evaluation + X-PAYMENT header construction.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

import httpx

from constraints import (
    Constraint,
    EvaluationContext,
    all_passed,
    evaluate_pre,
    first_failure,
)
from mandate import MandateClient

from .server import encode_payment_header


@dataclass
class AgentIdentity:
    agent_did: str
    # Hands-on simplification: Agent does not separately sign X-PAYMENT
    # (out-of-scope for Sprint 1; relies on Mandate signature only).


class PaymentBlocked(Exception):
    def __init__(self, reason: str, constraint_type: str):
        self.reason = reason
        self.constraint_type = constraint_type
        super().__init__(f"{constraint_type}: {reason}")


def build_payment_header(
    *,
    mandate_jwt: str,
    constraints: list[Constraint],
    requested_amount_usdc: float,
    merchant_id: str,
    platform: str,
    network: str = "mock-base",
    requested_at: int | None = None,
) -> str:
    requested_at = requested_at or int(time.time())
    # PRE self-eval (best-effort; Facilitator re-evaluates as authority)
    ctx = EvaluationContext(
        mandate_id=MandateClient.peek(mandate_jwt)["mandate_id"],
        requested_amount_usdc=requested_amount_usdc,
        merchant_id=merchant_id,
        platform=platform,
        requested_at=requested_at,
    )
    results = evaluate_pre(constraints, ctx)
    if not all_passed(results):
        f = first_failure(results)
        raise PaymentBlocked(reason=f.reason or "blocked", constraint_type=f.constraint_type)

    payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": network,
        "payload": {
            "mandate_ref_jwt": mandate_jwt,
            "amount": f"{requested_amount_usdc:.2f}",
            "asset": "USDC",
            "merchant_id": merchant_id,
            "platform": platform,
            "nonce": "0x" + secrets.token_hex(16),
        },
    }
    return encode_payment_header(payload)


async def pay(
    *,
    resource_url: str,
    mandate_jwt: str,
    constraints: list[Constraint],
    requested_amount_usdc: float,
    merchant_id: str,
    platform: str,
    client: httpx.AsyncClient,
) -> httpx.Response:
    header = build_payment_header(
        mandate_jwt=mandate_jwt,
        constraints=constraints,
        requested_amount_usdc=requested_amount_usdc,
        merchant_id=merchant_id,
        platform=platform,
    )
    return await client.get(resource_url, headers={"X-PAYMENT": header})
