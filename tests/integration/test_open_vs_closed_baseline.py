"""Open Mandate (multi-use) vs Closed Mandate (single-use) baseline comparison."""
from __future__ import annotations

import base64
import json

import httpx
import pytest
from httpx import ASGITransport

from x402.facilitator import FacilitatorState, create_app as create_facilitator
from x402.server import ResourceConfig


def _body_for(jwt, amount, merchant, platform, nonce):
    cfg = ResourceConfig(
        path="/buy/ad-impression-bundle",
        amount_usdc=amount,
        pay_to=merchant,
        platform=platform,
    )
    return {
        "x402Version": 1,
        "scheme": "exact",
        "network": "mock-base",
        "payload": {
            "mandate_ref_jwt": jwt,
            "amount": f"{amount:.2f}",
            "asset": "USDC",
            "merchant_id": merchant,
            "platform": platform,
            "nonce": nonce,
        },
        "paymentRequirements": cfg.payment_requirements(),
    }


@pytest.mark.asyncio
async def test_open_mandate_allows_multiple_settlements(user_kp, facilitator_kp, open_mandate_jwt):
    state = FacilitatorState({"did:user:0xUSER": user_kp.public}, facilitator_kp)
    app = create_facilitator(state)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://f") as cli:
        for i in range(3):
            body = _body_for(open_mandate_jwt, 30.0, "did:merchant:meta_ads", "meta_ads", nonce=f"0x{i:032x}")
            v = await cli.post("/verify", json=body)
            assert v.json()["verified"] is True, v.json()
            s = await cli.post("/settle", json=body)
            assert s.json()["success"] is True

        # Cumulative spend = 30 * 3 = 90
        st = next(iter(state.mandates.values()))
        assert st.cumulative_cost_usdc == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_closed_mandate_single_use_only(user_kp, facilitator_kp, closed_mandate_jwt):
    state = FacilitatorState({"did:user:0xUSER": user_kp.public}, facilitator_kp)
    app = create_facilitator(state)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://f") as cli:
        body = _body_for(closed_mandate_jwt, 30.0, "did:merchant:meta_ads", "meta_ads", nonce="0x" + "11" * 16)
        v1 = await cli.post("/verify", json=body)
        assert v1.json()["verified"] is True
        s1 = await cli.post("/settle", json=body)
        assert s1.json()["success"] is True

        # Second attempt with the same nonce fails
        v2 = await cli.post("/verify", json=body)
        assert v2.json()["verified"] is False
        assert v2.json()["invalid_reason_code"] == "NONCE_REPLAY"
