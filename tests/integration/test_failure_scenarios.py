"""
Failure scenarios covering 7 cases from the plan section 7.3.

1. Mandate signature forged
2. Mandate validity window violated
3. PRE Constraint violated
4. X-PAYMENT amount/merchant mismatch
5. Facilitator network mismatch
6. POST Constraint violated -> next attempt blocked
7. Closed Mandate nonce replay
"""
from __future__ import annotations

import base64
import json
import time

import httpx
import pytest
from httpx import ASGITransport

from constraints import (
    AllowedPlatforms,
    MaxCPA,
    MaxDailySpend,
    MaxPerTx,
    MinCTR,
    TimeWindow,
)
from mandate import (
    Keypair,
    MandateClient,
    MandateScope,
    build_closed_mandate,
    build_open_mandate,
)
from x402.client import build_payment_header
from x402.facilitator import FacilitatorState, create_app as create_facilitator
from x402.server import ResourceConfig


def _decode_header(h):
    return json.loads(base64.b64decode(h).decode())


def _body_for(jwt, amount, merchant, platform, network="mock-base"):
    cfg = ResourceConfig(
        path="/buy/ad-impression-bundle",
        amount_usdc=amount,
        pay_to=merchant,
        platform=platform,
    )
    return {
        "x402Version": 1,
        "scheme": "exact",
        "network": network,
        "payload": {
            "mandate_ref_jwt": jwt,
            "amount": f"{amount:.2f}",
            "asset": "USDC",
            "merchant_id": merchant,
            "platform": platform,
            "nonce": "0x" + "ab" * 16,
        },
        "paymentRequirements": cfg.payment_requirements(),
    }


@pytest.fixture
def fac_setup(user_kp, facilitator_kp):
    state = FacilitatorState(
        user_pubkeys={"did:user:0xUSER": user_kp.public},
        facilitator_kp=facilitator_kp,
    )
    app = create_facilitator(state)
    return state, app


# 1. Forged signature ----------------------------------------------------------

@pytest.mark.asyncio
async def test_forged_signature_rejected(fac_setup, attacker_kp, standard_constraints):
    state, app = fac_setup
    # Sign with attacker_kp instead of user_kp
    payload = build_open_mandate(
        issuer="did:user:0xUSER",
        subject="did:agent:0xAGENT",
        scope=MandateScope(purpose="malicious"),
        constraints=standard_constraints,
    ).model_dump()
    bad_jwt = MandateClient.sign(payload, attacker_kp)

    body = _body_for(bad_jwt, 30.0, "did:merchant:meta_ads", "meta_ads")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://f") as cli:
        r = await cli.post("/verify", json=body)
        d = r.json()
        assert d["verified"] is False
        assert d["invalid_reason_code"] == "MANDATE_SIGNATURE_INVALID"


# 2. Validity window -----------------------------------------------------------

@pytest.mark.asyncio
async def test_expired_mandate_rejected(fac_setup, user_kp, standard_constraints):
    state, app = fac_setup
    # Build a mandate with valid_until in the past
    payload = build_open_mandate(
        issuer="did:user:0xUSER",
        subject="did:agent:0xAGENT",
        scope=MandateScope(purpose="ad_campaign_q2"),
        constraints=standard_constraints,
    ).model_dump()
    payload["valid_from"] = int(time.time()) - 7200
    payload["valid_until"] = int(time.time()) - 3600
    expired_jwt = MandateClient.sign(payload, user_kp)

    body = _body_for(expired_jwt, 30.0, "did:merchant:meta_ads", "meta_ads")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://f") as cli:
        r = await cli.post("/verify", json=body)
        d = r.json()
        assert d["verified"] is False
        assert d["invalid_reason_code"] == "MANDATE_EXPIRED_OR_FUTURE"


# 3. PRE constraint violations ------------------------------------------------

@pytest.mark.asyncio
async def test_per_tx_limit_violation(fac_setup, open_mandate_jwt):
    state, app = fac_setup
    body = _body_for(open_mandate_jwt, 99.0, "did:merchant:meta_ads", "meta_ads")  # > 50
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://f") as cli:
        r = await cli.post("/verify", json=body)
        d = r.json()
        assert d["verified"] is False
        assert d["invalid_reason_code"] == "PRE_CONSTRAINT_FAILED"
        assert "max_per_tx" in d["reason"]


@pytest.mark.asyncio
async def test_platform_not_allowed(fac_setup, open_mandate_jwt):
    state, app = fac_setup
    body = _body_for(open_mandate_jwt, 30.0, "did:merchant:naver", "naver_searchad")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://f") as cli:
        r = await cli.post("/verify", json=body)
        d = r.json()
        assert d["verified"] is False
        assert "allowed_platforms" in d["reason"]


# 4. X-PAYMENT amount/merchant mismatch with paymentRequirements --------------

@pytest.mark.asyncio
async def test_amount_mismatch(fac_setup, open_mandate_jwt):
    state, app = fac_setup
    body = _body_for(open_mandate_jwt, 30.0, "did:merchant:meta_ads", "meta_ads")
    body["paymentRequirements"]["maxAmountRequired"] = "31.00"  # tampered
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://f") as cli:
        r = await cli.post("/verify", json=body)
        d = r.json()
        assert d["verified"] is False
        assert d["invalid_reason_code"] == "PAYLOAD_AMOUNT_MISMATCH"


@pytest.mark.asyncio
async def test_merchant_mismatch(fac_setup, open_mandate_jwt):
    state, app = fac_setup
    body = _body_for(open_mandate_jwt, 30.0, "did:merchant:meta_ads", "meta_ads")
    body["paymentRequirements"]["payTo"] = "did:merchant:OTHER"
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://f") as cli:
        r = await cli.post("/verify", json=body)
        d = r.json()
        assert d["verified"] is False
        assert d["invalid_reason_code"] == "PAYLOAD_MERCHANT_MISMATCH"


# 5. Facilitator network mismatch ---------------------------------------------

@pytest.mark.asyncio
async def test_network_mismatch(fac_setup, open_mandate_jwt):
    state, app = fac_setup
    body = _body_for(open_mandate_jwt, 30.0, "did:merchant:meta_ads", "meta_ads", network="ethereum-mainnet")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://f") as cli:
        r = await cli.post("/verify", json=body)
        d = r.json()
        assert d["verified"] is False
        assert d["invalid_reason_code"] == "NETWORK_MISMATCH"


# 6. POST violation -> blocks next PRE ----------------------------------------

@pytest.mark.asyncio
async def test_post_violation_blocks_next_attempt(fac_setup, open_mandate_jwt, user_kp):
    state, app = fac_setup
    # Push KPI that violates MaxCPA: cost=200, conversions=10 -> CPA=20 > 12
    mandate_payload = MandateClient.peek(open_mandate_jwt)
    mandate_id = mandate_payload["mandate_id"]

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://f") as cli:
        await cli.post("/kpi/push", json={
            "mandate_id": mandate_id,
            "cost_usdc": 200,
            "conversions": 10,
            "clicks": 200,
            "impressions": 10000,
        })
        # Run POST evaluation
        pe = await cli.post("/post_eval", json={
            "mandate_id": mandate_id,
            "mandate_jwt": open_mandate_jwt,
        })
        assert pe.json()["passed"] is False
        assert pe.json()["blocked"] is True

        # Subsequent verify should be blocked
        body = _body_for(open_mandate_jwt, 30.0, "did:merchant:meta_ads", "meta_ads")
        r = await cli.post("/verify", json=body)
        d = r.json()
        assert d["verified"] is False
        assert d["invalid_reason_code"] == "POST_BLOCKED"


# 7. Closed Mandate nonce replay ---------------------------------------------

@pytest.mark.asyncio
async def test_closed_mandate_nonce_replay(fac_setup, closed_mandate_jwt):
    state, app = fac_setup
    body = _body_for(closed_mandate_jwt, 30.0, "did:merchant:meta_ads", "meta_ads")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://f") as cli:
        # First settle: should succeed
        v1 = await cli.post("/verify", json=body)
        assert v1.json()["verified"] is True
        s1 = await cli.post("/settle", json=body)
        assert s1.json()["success"] is True

        # Replay with same nonce: must fail
        v2 = await cli.post("/verify", json=body)
        d = v2.json()
        assert d["verified"] is False
        assert d["invalid_reason_code"] == "NONCE_REPLAY"
