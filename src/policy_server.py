"""
Policy server entry-points.

Per 0503 briefing: macro (Mandate constraints) and micro (per-tx) layered.
This module is invoked by the Facilitator to evaluate PRE/POST constraints
against accumulated state. The accumulator lives in the Facilitator process
to keep "x402 verify + policy eval" inside one trust boundary (no MITM).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from constraints import (
    ConstraintBase,
    EvaluationContext,
    EvaluationResult,
    all_passed,
    evaluate_post,
    evaluate_pre,
    first_failure,
)


@dataclass
class MandateRuntimeState:
    """Per-mandate accumulator (in-memory only for hands-on)."""

    mandate_id: str
    blocked: bool = False
    block_reason: str | None = None
    daily_spend_by_date: dict[str, float] = field(default_factory=dict)
    cumulative_cost_usdc: float = 0.0
    cumulative_conversions: int = 0
    cumulative_clicks: int = 0
    cumulative_impressions: int = 0
    used_nonces: set[str] = field(default_factory=set)

    def daily_spend(self, ts: int) -> float:
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        return self.daily_spend_by_date.get(d, 0.0)

    def add_spend(self, ts: int, amount: float) -> None:
        d = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        self.daily_spend_by_date[d] = self.daily_spend_by_date.get(d, 0.0) + amount
        self.cumulative_cost_usdc += amount


def build_context(
    mandate_id: str,
    requested_amount_usdc: float,
    merchant_id: str,
    platform: str,
    requested_at: int,
    state: MandateRuntimeState,
) -> EvaluationContext:
    return EvaluationContext(
        mandate_id=mandate_id,
        requested_amount_usdc=requested_amount_usdc,
        merchant_id=merchant_id,
        platform=platform,
        requested_at=requested_at,
        daily_spend_so_far=state.daily_spend(requested_at),
        cumulative_cost_usdc=state.cumulative_cost_usdc,
        cumulative_conversions=state.cumulative_conversions,
        cumulative_clicks=state.cumulative_clicks,
        cumulative_impressions=state.cumulative_impressions,
    )


def run_pre(
    constraints: list[ConstraintBase], ctx: EvaluationContext
) -> tuple[bool, list[EvaluationResult]]:
    results = evaluate_pre(constraints, ctx)
    return all_passed(results), results


def run_post(
    constraints: list[ConstraintBase], ctx: EvaluationContext
) -> tuple[bool, list[EvaluationResult]]:
    results = evaluate_post(constraints, ctx)
    return all_passed(results), results


__all__ = [
    "MandateRuntimeState",
    "build_context",
    "first_failure",
    "run_post",
    "run_pre",
]
