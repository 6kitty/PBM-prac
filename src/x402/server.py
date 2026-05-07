"""
Mock Resource Server (FastAPI app) for x402.

Returns 402 Payment Required + paymentRequirements when X-PAYMENT is missing,
forwards X-PAYMENT to the Facilitator's /verify and /settle when present.
"""
from __future__ import annotations

import base64
import json

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse


def encode_payment_header(payload: dict) -> str:
    return base64.b64encode(json.dumps(payload).encode()).decode("ascii")


def decode_payment_header(value: str) -> dict:
    return json.loads(base64.b64decode(value).decode())


class ResourceConfig:
    def __init__(
        self,
        path: str,
        amount_usdc: float,
        pay_to: str,
        platform: str,
        network: str = "mock-base",
        asset: str = "USDC",
    ):
        self.path = path
        self.amount_usdc = amount_usdc
        self.pay_to = pay_to
        self.platform = platform
        self.network = network
        self.asset = asset

    def payment_requirements(self) -> dict:
        return {
            "scheme": "exact",
            "network": self.network,
            "asset": self.asset,
            "maxAmountRequired": f"{self.amount_usdc:.2f}",
            "payTo": self.pay_to,
            "resource": self.path,
            "extra": {"requires_mandate": True, "platform": self.platform},
        }


def create_app(
    facilitator_base_url: str,
    resources: list[ResourceConfig],
) -> FastAPI:
    app = FastAPI(title="ap2-pbm-handson resource server (mock)")
    by_path = {r.path: r for r in resources}

    @app.get("/buy/{name}")
    async def buy(name: str, request: Request, x_payment: str | None = Header(default=None)):
        path = f"/buy/{name}"
        cfg = by_path.get(path)
        if cfg is None:
            return JSONResponse(status_code=404, content={"error": "unknown_resource"})
        reqs = cfg.payment_requirements()

        if x_payment is None:
            return JSONResponse(
                status_code=402,
                content={"x402Version": 1, "accepts": [reqs]},
            )

        try:
            payment_payload = decode_payment_header(x_payment)
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"error": "x_payment_undecodable"},
            )

        body = {
            "x402Version": 1,
            "scheme": payment_payload.get("scheme", "exact"),
            "network": payment_payload.get("network", cfg.network),
            "payload": payment_payload.get("payload", payment_payload),
            "paymentRequirements": reqs,
        }

        async with httpx.AsyncClient(base_url=facilitator_base_url) as cli:
            verify_resp = await cli.post("/verify", json=body)
            verify_data = verify_resp.json()
            if not verify_data.get("verified"):
                # Re-issue 402 with the failure reason for visibility
                return JSONResponse(
                    status_code=402,
                    content={
                        "x402Version": 1,
                        "accepts": [reqs],
                        "error": verify_data.get("reason"),
                        "invalid_reason_code": verify_data.get("invalid_reason_code"),
                    },
                )
            settle_resp = await cli.post("/settle", json=body)
            settle_data = settle_resp.json()
            if not settle_data.get("success"):
                return JSONResponse(
                    status_code=502,
                    content={"error": settle_data.get("reason", "settle_failed")},
                )

        return {
            "ok": True,
            "resource": path,
            "amount_paid_usdc": float(body["payload"]["amount"]),
            "receipt": settle_data.get("receipt"),
        }

    return app
