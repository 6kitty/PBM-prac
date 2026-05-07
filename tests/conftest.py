"""Shared fixtures."""
from __future__ import annotations

import time
from typing import Iterator

import pytest

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


@pytest.fixture
def user_kp() -> Keypair:
    return Keypair.generate()


@pytest.fixture
def attacker_kp() -> Keypair:
    return Keypair.generate()


@pytest.fixture
def facilitator_kp() -> Keypair:
    return Keypair.generate()


@pytest.fixture
def standard_constraints() -> list:
    return [
        MaxDailySpend(limit_usdc=500),
        MaxPerTx(limit_usdc=50),
        TimeWindow(start_hour=0, end_hour=24 - 1, timezone="UTC"),
        AllowedPlatforms(platforms=["meta_ads", "google_ads"]),
        MaxCPA(threshold_usdc=12, min_conversions_for_eval=10),
        MinCTR(threshold_pct=1.0, min_impressions_for_eval=1000),
    ]


@pytest.fixture
def open_mandate_jwt(user_kp, standard_constraints) -> str:
    payload = build_open_mandate(
        issuer="did:user:0xUSER",
        subject="did:agent:0xAGENT",
        scope=MandateScope(purpose="ad_campaign_q2", campaign_id="cmp_test"),
        constraints=standard_constraints,
    ).model_dump()
    return MandateClient.sign(payload, user_kp)


@pytest.fixture
def open_mandate_payload(user_kp, standard_constraints) -> dict:
    return build_open_mandate(
        issuer="did:user:0xUSER",
        subject="did:agent:0xAGENT",
        scope=MandateScope(purpose="ad_campaign_q2", campaign_id="cmp_test"),
        constraints=standard_constraints,
    ).model_dump()


@pytest.fixture
def closed_mandate_jwt(user_kp, standard_constraints) -> str:
    payload = build_closed_mandate(
        issuer="did:user:0xUSER",
        subject="did:agent:0xAGENT",
        scope=MandateScope(purpose="ad_campaign_q2_oneoff"),
        constraints=standard_constraints,
        merchant_id="did:merchant:meta_ads",
        amount_usdc=30.00,
        cart_id="cart_42",
    ).model_dump()
    return MandateClient.sign(payload, user_kp)
