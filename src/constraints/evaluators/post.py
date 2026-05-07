"""
POST-evaluation Evaluators (2 types).

POST evaluators read cumulative_* fields populated from external KPI feed.
If sample size is insufficient (`min_*_for_eval`), result is `passed=True`
with reason="insufficient_sample" so it does not falsely block traffic
before enough data is gathered.
"""
from __future__ import annotations

from ..registry import ConstraintRegistry
from ..schema import EvaluationContext, EvaluationResult, MaxCPA, MinCTR


@ConstraintRegistry.register("max_cpa")
class MaxCPAEvaluator:
    def evaluate(self, c: MaxCPA, ctx: EvaluationContext) -> EvaluationResult:
        if ctx.cumulative_conversions < c.min_conversions_for_eval:
            return EvaluationResult(
                passed=True,
                constraint_type=c.type,
                timing="POST",
                reason=f"insufficient_sample: conversions={ctx.cumulative_conversions} < {c.min_conversions_for_eval}",
            )
        cpa = ctx.cumulative_cost_usdc / ctx.cumulative_conversions
        ok = cpa <= c.threshold_usdc
        return EvaluationResult(
            passed=ok,
            constraint_type=c.type,
            timing="POST",
            reason=None
            if ok
            else f"cpa_exceeded: {cpa:.4f}/{c.threshold_usdc} (window={c.window})",
        )


@ConstraintRegistry.register("min_ctr")
class MinCTREvaluator:
    def evaluate(self, c: MinCTR, ctx: EvaluationContext) -> EvaluationResult:
        if ctx.cumulative_impressions < c.min_impressions_for_eval:
            return EvaluationResult(
                passed=True,
                constraint_type=c.type,
                timing="POST",
                reason=f"insufficient_sample: impressions={ctx.cumulative_impressions} < {c.min_impressions_for_eval}",
            )
        ctr_pct = (ctx.cumulative_clicks / ctx.cumulative_impressions) * 100
        ok = ctr_pct >= c.threshold_pct
        return EvaluationResult(
            passed=ok,
            constraint_type=c.type,
            timing="POST",
            reason=None
            if ok
            else f"ctr_below_threshold: {ctr_pct:.4f}%/{c.threshold_pct}% (window={c.window})",
        )
