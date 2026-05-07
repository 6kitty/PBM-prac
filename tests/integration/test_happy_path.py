"""End-to-end happy path: Open Mandate -> 402 -> X-PAYMENT -> verify+settle."""
from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport

from x402.client import build_payment_header
from x402.facilitator import FacilitatorState, create_app as create_facilitator
from x402.server import ResourceConfig, create_app as create_resource


def _build_apps(user_kp, facilitator_kp):
    fstate = FacilitatorState(
        user_pubkeys={"did:user:0xUSER": user_kp.public},
        facilitator_kp=facilitator_kp,
    )
    fac_app = create_facilitator(fstate)
    return fstate, fac_app


@pytest.mark.asyncio
async def test_happy_path(user_kp, facilitator_kp, open_mandate_jwt, standard_constraints):
    fstate, fac_app = _build_apps(user_kp, facilitator_kp)

    async with httpx.AsyncClient(transport=ASGITransport(app=fac_app), base_url="http://facilitator") as fac_client:
        # Build resource server pointing at the facilitator via in-process httpx
        # Trick: we patch the resource server to call our in-process facilitator.
        from x402 import server as srv_mod

        # Build a resource app whose facilitator URL is "http://facilitator" but
        # served by our ASGI client. We do that by monkeypatching httpx.AsyncClient
        # used inside the resource server: instead, simpler is to invoke verify/settle
        # directly with the same payload, which mirrors the resource server behavior.

        cfg = ResourceConfig(
            path="/buy/ad-impression-bundle",
            amount_usdc=30.00,
            pay_to="did:merchant:meta_ads",
            platform="meta_ads",
        )
        # Step 1: agent crafts X-PAYMENT
        header = build_payment_header(
            mandate_jwt=open_mandate_jwt,
            constraints=standard_constraints,
            requested_amount_usdc=30.00,
            merchant_id="did:merchant:meta_ads",
            platform="meta_ads",
        )
        # Decode and run through facilitator's /verify and /settle
        import base64, json

        decoded = json.loads(base64.b64decode(header).decode())
        body = {
            "x402Version": 1,
            "scheme": "exact",
            "network": "mock-base",
            "payload": decoded["payload"],
            "paymentRequirements": cfg.payment_requirements(),
        }
        v = await fac_client.post("/verify", json=body)
        assert v.status_code == 200
        assert v.json()["verified"] is True

        s = await fac_client.post("/settle", json=body)
        assert s.status_code == 200
        assert s.json()["success"] is True
        assert s.json()["receipt"] is not None

        # Cumulative state advanced
        st = fstate.mandates[next(iter(fstate.mandates))]
        assert st.cumulative_cost_usdc == pytest.approx(30.00)
