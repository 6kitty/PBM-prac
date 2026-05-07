"""POST Evaluator unit tests."""
from __future__ import annotations

from constraints import ConstraintRegistry, EvaluationContext, MaxCPA, MinCTR


def _ctx(**kw):
    base = dict(
        mandate_id="mnd_test",
        requested_amount_usdc=0.0,
        merchant_id="",
        platform="",
        requested_at=1746518400,
    )
    base.update(kw)
    return EvaluationContext(**base)


class TestMaxCPA:
    def test_insufficient_sample_passes(self):
        e = ConstraintRegistry.get("max_cpa")
        r = e.evaluate(
            MaxCPA(threshold_usdc=12, min_conversions_for_eval=10),
            _ctx(cumulative_cost_usdc=200, cumulative_conversions=5),
        )
        assert r.passed
        assert "insufficient_sample" in r.reason

    def test_under_threshold_passes(self):
        e = ConstraintRegistry.get("max_cpa")
        # 10 conversions, $100 -> CPA $10
        r = e.evaluate(
            MaxCPA(threshold_usdc=12, min_conversions_for_eval=10),
            _ctx(cumulative_cost_usdc=100, cumulative_conversions=10),
        )
        assert r.passed

    def test_at_threshold_passes(self):
        e = ConstraintRegistry.get("max_cpa")
        r = e.evaluate(
            MaxCPA(threshold_usdc=12, min_conversions_for_eval=10),
            _ctx(cumulative_cost_usdc=120, cumulative_conversions=10),
        )
        assert r.passed  # CPA = 12 == threshold

    def test_over_threshold_fails(self):
        e = ConstraintRegistry.get("max_cpa")
        r = e.evaluate(
            MaxCPA(threshold_usdc=12, min_conversions_for_eval=10),
            _ctx(cumulative_cost_usdc=130, cumulative_conversions=10),
        )
        assert not r.passed
        assert "cpa_exceeded" in r.reason


class TestMinCTR:
    def test_insufficient_sample_passes(self):
        e = ConstraintRegistry.get("min_ctr")
        r = e.evaluate(
            MinCTR(threshold_pct=1.0, min_impressions_for_eval=1000),
            _ctx(cumulative_clicks=5, cumulative_impressions=500),
        )
        assert r.passed
        assert "insufficient_sample" in r.reason

    def test_above_threshold_passes(self):
        e = ConstraintRegistry.get("min_ctr")
        # 20 / 1000 = 2% > 1%
        r = e.evaluate(
            MinCTR(threshold_pct=1.0, min_impressions_for_eval=1000),
            _ctx(cumulative_clicks=20, cumulative_impressions=1000),
        )
        assert r.passed

    def test_at_threshold_passes(self):
        e = ConstraintRegistry.get("min_ctr")
        # exactly 1.0%
        r = e.evaluate(
            MinCTR(threshold_pct=1.0, min_impressions_for_eval=1000),
            _ctx(cumulative_clicks=10, cumulative_impressions=1000),
        )
        assert r.passed

    def test_below_threshold_fails(self):
        e = ConstraintRegistry.get("min_ctr")
        r = e.evaluate(
            MinCTR(threshold_pct=1.0, min_impressions_for_eval=1000),
            _ctx(cumulative_clicks=5, cumulative_impressions=1000),
        )
        assert not r.passed
        assert "ctr_below_threshold" in r.reason
