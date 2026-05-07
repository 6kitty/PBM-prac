"""
PRE-evaluation Evaluators (4 types).

These run synchronously at payment-attempt time.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..registry import ConstraintRegistry
from ..schema import (
    AllowedPlatforms,
    EvaluationContext,
    EvaluationResult,
    MaxDailySpend,
    MaxPerTx,
    TimeWindow,
)


@ConstraintRegistry.register("max_daily_spend")
class MaxDailySpendEvaluator:
    def evaluate(
        self, c: MaxDailySpend, ctx: EvaluationContext
    ) -> EvaluationResult:
        projected = ctx.daily_spend_so_far + ctx.requested_amount_usdc
        ok = projected <= c.limit_usdc
        return EvaluationResult(
            passed=ok,
            constraint_type=c.type,
            timing="PRE",
            reason=None
            if ok
            else f"daily_spend_exceeded: {projected}/{c.limit_usdc}",
        )


@ConstraintRegistry.register("max_per_tx")
class MaxPerTxEvaluator:
    def evaluate(self, c: MaxPerTx, ctx: EvaluationContext) -> EvaluationResult:
        ok = ctx.requested_amount_usdc <= c.limit_usdc
        return EvaluationResult(
            passed=ok,
            constraint_type=c.type,
            timing="PRE",
            reason=None
            if ok
            else f"per_tx_exceeded: {ctx.requested_amount_usdc}/{c.limit_usdc}",
        )


@ConstraintRegistry.register("time_window")
class TimeWindowEvaluator:
    def evaluate(
        self, c: TimeWindow, ctx: EvaluationContext
    ) -> EvaluationResult:
        tz = ZoneInfo(c.timezone)
        local = datetime.fromtimestamp(ctx.requested_at, tz=tz)
        h = local.hour
        if c.start_hour <= c.end_hour:
            ok = c.start_hour <= h < c.end_hour
        else:
            # window crosses midnight (e.g., 22 -> 6)
            ok = h >= c.start_hour or h < c.end_hour
        return EvaluationResult(
            passed=ok,
            constraint_type=c.type,
            timing="PRE",
            reason=None
            if ok
            else f"time_window_violated: hour={h} window=[{c.start_hour},{c.end_hour}) tz={c.timezone}",
        )


@ConstraintRegistry.register("allowed_platforms")
class AllowedPlatformsEvaluator:
    def evaluate(
        self, c: AllowedPlatforms, ctx: EvaluationContext
    ) -> EvaluationResult:
        ok = ctx.platform in c.platforms
        return EvaluationResult(
            passed=ok,
            constraint_type=c.type,
            timing="PRE",
            reason=None
            if ok
            else f"platform_not_allowed: {ctx.platform} not in {c.platforms}",
        )
