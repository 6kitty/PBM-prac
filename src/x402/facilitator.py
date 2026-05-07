"""
Mock x402 Facilitator (FastAPI app).

Trust boundary holding:
- Mandate signature verification (via MandateClient)
- PRE constraint re-evaluation (via policy_server)
- Cumulative state for POST evaluation
- Receipt issuance
"""
from __future__ import annotations

import time
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI
from pydantic import BaseModel

from mandate import (
    InvalidMandateSignature,
    Keypair,
    MandateClient,
    ReceiptClient,
)
from policy_server import (
    MandateRuntimeState,
    build_context,
    first_failure,
    run_post,
    run_pre,
)

# Pydantic models import the discriminated Constraint union via re-construct
from constraints.schema import (
    AllowedPlatforms,
    Constraint,
    MaxCPA,
    MaxDailySpend,
    MaxPerTx,
    MinCTR,
    TimeWindow,
)


_CONSTRAINT_MODELS = {
    "max_daily_spend": MaxDailySpend,
    "max_per_tx": MaxPerTx,
    "time_window": TimeWindow,
    "allowed_platforms": AllowedPlatforms,
    "max_cpa": MaxCPA,
    "min_ctr": MinCTR,
}


def _materialize_constraints(raw: list[dict]) -> list[Constraint]:
    out: list[Any] = []
    for r in raw:
        cls = _CONSTRAINT_MODELS.get(r.get("type"))
        if cls is None:
            raise ValueError(f"unknown_constraint_type: {r.get('type')}")
        out.append(cls(**r))
    return out


# --- Request / Response models ----------------------------------------------

class VerifyRequest(BaseModel):
    x402Version: int
    scheme: str
    network: str
    payload: dict
    paymentRequirements: dict


class VerifyResponse(BaseModel):
    verified: bool
    reason: str | None = None
    invalid_reason_code: str | None = None
    pre_results: list[dict] | None = None


class SettleRequest(BaseModel):
    x402Version: int
    scheme: str
    network: str
    payload: dict
    paymentRequirements: dict


class SettleResponse(BaseModel):
    success: bool
    receipt: str | None = None
    reason: str | None = None


class KpiPushRequest(BaseModel):
    mandate_id: str
    cost_usdc: float = 0.0
    conversions: int = 0
    clicks: int = 0
    impressions: int = 0


class PostEvalRequest(BaseModel):
    mandate_id: str
    # The accumulator is the source of truth; constraints come from the mandate
    mandate_jwt: str


class PostEvalResponse(BaseModel):
    passed: bool
    blocked: bool
    block_reason: str | None = None
    results: list[dict]


# --- Facilitator state -------------------------------------------------------

class FacilitatorState:
    def __init__(self, user_pubkeys: dict[str, Ed25519PublicKey], facilitator_kp: Keypair):
        self.user_pubkeys = user_pubkeys  # issuer -> pubkey
        self.facilitator_kp = facilitator_kp
        self.mandates: dict[str, MandateRuntimeState] = {}

    def state_for(self, mandate_id: str) -> MandateRuntimeState:
        if mandate_id not in self.mandates:
            self.mandates[mandate_id] = MandateRuntimeState(mandate_id=mandate_id)
        return self.mandates[mandate_id]


# --- App factory -------------------------------------------------------------

def create_app(state: FacilitatorState) -> FastAPI:
    app = FastAPI(title="ap2-pbm-handson facilitator (mock)")

    @app.post("/verify", response_model=VerifyResponse)
    def verify(req: VerifyRequest) -> VerifyResponse:
        # 1. Decode and verify Mandate signature
        mandate_jwt = req.payload.get("mandate_ref_jwt")
        if not mandate_jwt:
            return VerifyResponse(
                verified=False,
                reason="missing_mandate_ref_jwt",
                invalid_reason_code="MANDATE_MISSING",
            )
        # peek issuer first
        try:
            unverified = MandateClient.peek(mandate_jwt)
        except Exception:
            return VerifyResponse(
                verified=False,
                reason="malformed_mandate_jwt",
                invalid_reason_code="MANDATE_MALFORMED",
            )
        issuer = unverified.get("issuer")
        pubkey = state.user_pubkeys.get(issuer)
        if pubkey is None:
            return VerifyResponse(
                verified=False,
                reason=f"unknown_issuer:{issuer}",
                invalid_reason_code="MANDATE_ISSUER_UNKNOWN",
            )
        try:
            mandate = MandateClient.verify(mandate_jwt, pubkey)
        except InvalidMandateSignature as e:
            return VerifyResponse(
                verified=False,
                reason=f"signature_invalid:{e}",
                invalid_reason_code="MANDATE_SIGNATURE_INVALID",
            )

        now = int(time.time())
        # 2. Validity window
        if not (mandate["valid_from"] <= now <= mandate["valid_until"]):
            return VerifyResponse(
                verified=False,
                reason="mandate_not_in_validity_window",
                invalid_reason_code="MANDATE_EXPIRED_OR_FUTURE",
            )

        # 3. Nonce replay (Closed Mandate single-use)
        rt = state.state_for(mandate["mandate_id"])
        nonce = req.payload.get("nonce")
        if mandate["type"] == "closed" and nonce in rt.used_nonces:
            return VerifyResponse(
                verified=False,
                reason="nonce_replay",
                invalid_reason_code="NONCE_REPLAY",
            )

        # 4. paymentRequirements <-> X-PAYMENT consistency
        pr = req.paymentRequirements
        py = req.payload
        if str(py.get("amount")) != str(pr.get("maxAmountRequired")):
            return VerifyResponse(
                verified=False,
                reason=f"amount_mismatch:{py.get('amount')}!={pr.get('maxAmountRequired')}",
                invalid_reason_code="PAYLOAD_AMOUNT_MISMATCH",
            )
        if py.get("merchant_id") != pr.get("payTo"):
            return VerifyResponse(
                verified=False,
                reason="merchant_mismatch",
                invalid_reason_code="PAYLOAD_MERCHANT_MISMATCH",
            )
        if req.network != pr.get("network"):
            return VerifyResponse(
                verified=False,
                reason="network_mismatch",
                invalid_reason_code="NETWORK_MISMATCH",
            )

        # 5. Closed Mandate cart binding
        if mandate["type"] == "closed":
            if mandate["merchant_id"] != py["merchant_id"]:
                return VerifyResponse(
                    verified=False,
                    reason="closed_mandate_merchant_mismatch",
                    invalid_reason_code="CLOSED_MANDATE_BINDING",
                )
            if float(mandate["amount_usdc"]) != float(py["amount"]):
                return VerifyResponse(
                    verified=False,
                    reason="closed_mandate_amount_mismatch",
                    invalid_reason_code="CLOSED_MANDATE_BINDING",
                )

        # 6. Block flag from prior POST evaluation
        if rt.blocked:
            return VerifyResponse(
                verified=False,
                reason=f"mandate_blocked:{rt.block_reason}",
                invalid_reason_code="POST_BLOCKED",
            )

        # 7. PRE constraint re-evaluation
        constraints = _materialize_constraints(mandate["constraints"])
        ctx = build_context(
            mandate_id=mandate["mandate_id"],
            requested_amount_usdc=float(py["amount"]),
            merchant_id=py["merchant_id"],
            platform=pr.get("extra", {}).get("platform", py.get("platform", "")),
            requested_at=now,
            state=rt,
        )
        ok, results = run_pre(constraints, ctx)
        if not ok:
            f = first_failure(results)
            return VerifyResponse(
                verified=False,
                reason=f"pre_constraint_failed:{f.constraint_type}:{f.reason}",
                invalid_reason_code="PRE_CONSTRAINT_FAILED",
                pre_results=[r.model_dump() for r in results],
            )

        return VerifyResponse(verified=True, pre_results=[r.model_dump() for r in results])

    @app.post("/settle", response_model=SettleResponse)
    def settle(req: SettleRequest) -> SettleResponse:
        # Re-verify and then commit
        v = verify(VerifyRequest(**req.model_dump()))
        if not v.verified:
            return SettleResponse(success=False, reason=v.reason)
        py = req.payload
        mandate_jwt = py["mandate_ref_jwt"]
        unverified = MandateClient.peek(mandate_jwt)
        rt = state.state_for(unverified["mandate_id"])
        now = int(time.time())
        rt.add_spend(now, float(py["amount"]))
        if py.get("nonce"):
            rt.used_nonces.add(py["nonce"])
        receipt = ReceiptClient.create(
            payload={
                "receipt_id": f"rcpt_{int(time.time() * 1000)}",
                "mandate_id": unverified["mandate_id"],
                "amount_usdc": float(py["amount"]),
                "merchant_id": py["merchant_id"],
                "settled_at": now,
                "tx_hash_mock": "0x" + "00" * 16,
            },
            kp=state.facilitator_kp,
        )
        return SettleResponse(success=True, receipt=receipt)

    @app.post("/kpi/push")
    def kpi_push(req: KpiPushRequest) -> dict:
        rt = state.state_for(req.mandate_id)
        rt.cumulative_cost_usdc += req.cost_usdc
        rt.cumulative_conversions += req.conversions
        rt.cumulative_clicks += req.clicks
        rt.cumulative_impressions += req.impressions
        return {"ok": True, "state": {
            "cost": rt.cumulative_cost_usdc,
            "conversions": rt.cumulative_conversions,
            "clicks": rt.cumulative_clicks,
            "impressions": rt.cumulative_impressions,
        }}

    @app.post("/post_eval", response_model=PostEvalResponse)
    def post_eval(req: PostEvalRequest) -> PostEvalResponse:
        unverified = MandateClient.peek(req.mandate_jwt)
        constraints = _materialize_constraints(unverified["constraints"])
        rt = state.state_for(req.mandate_id)
        now = int(time.time())
        ctx = build_context(
            mandate_id=req.mandate_id,
            requested_amount_usdc=0.0,
            merchant_id="",
            platform="",
            requested_at=now,
            state=rt,
        )
        ok, results = run_post(constraints, ctx)
        if not ok:
            f = first_failure(results)
            rt.blocked = True
            rt.block_reason = f"{f.constraint_type}:{f.reason}"
        return PostEvalResponse(
            passed=ok,
            blocked=rt.blocked,
            block_reason=rt.block_reason,
            results=[r.model_dump() for r in results],
        )

    return app
