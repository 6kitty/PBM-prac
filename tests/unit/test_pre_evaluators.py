"""
PRE Evaluator unit tests.

Notion task: Constraint Evaluator 단위 테스트
- 타입별 정상/경계값/위반 케이스 최소 3개씩
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from constraints import (
    AllowedPlatforms,
    ConstraintRegistry,
    EvaluationContext,
    MaxDailySpend,
    MaxPerTx,
    TimeWindow,
)


def _ctx(**kw):
    base = dict(
        mandate_id="mnd_test",
        requested_amount_usdc=10.0,
        merchant_id="did:merchant:meta_ads",
        platform="meta_ads",
        requested_at=int(datetime(2026, 5, 6, 12, 0, tzinfo=ZoneInfo("UTC")).timestamp()),
    )
    base.update(kw)
    return EvaluationContext(**base)


# --- MaxDailySpend ----------------------------------------------------------

class TestMaxDailySpend:
    def test_under_limit_passes(self):
        e = ConstraintRegistry.get("max_daily_spend")
        r = e.evaluate(MaxDailySpend(limit_usdc=500), _ctx(daily_spend_so_far=100, requested_amount_usdc=50))
        assert r.passed

    def test_exact_limit_passes(self):
        e = ConstraintRegistry.get("max_daily_spend")
        r = e.evaluate(MaxDailySpend(limit_usdc=500), _ctx(daily_spend_so_far=450, requested_amount_usdc=50))
        assert r.passed  # boundary: equal-to-limit allowed

    def test_over_limit_fails(self):
        e = ConstraintRegistry.get("max_daily_spend")
        r = e.evaluate(MaxDailySpend(limit_usdc=500), _ctx(daily_spend_so_far=480, requested_amount_usdc=50))
        assert not r.passed
        assert "daily_spend_exceeded" in r.reason


# --- MaxPerTx ---------------------------------------------------------------

class TestMaxPerTx:
    def test_under_limit_passes(self):
        e = ConstraintRegistry.get("max_per_tx")
        r = e.evaluate(MaxPerTx(limit_usdc=50), _ctx(requested_amount_usdc=49.99))
        assert r.passed

    def test_exact_limit_passes(self):
        e = ConstraintRegistry.get("max_per_tx")
        r = e.evaluate(MaxPerTx(limit_usdc=50), _ctx(requested_amount_usdc=50))
        assert r.passed

    def test_over_limit_fails(self):
        e = ConstraintRegistry.get("max_per_tx")
        r = e.evaluate(MaxPerTx(limit_usdc=50), _ctx(requested_amount_usdc=50.01))
        assert not r.passed


# --- TimeWindow -------------------------------------------------------------

def _at(year, month, day, hour, tz="Asia/Seoul"):
    return int(datetime(year, month, day, hour, 0, tzinfo=ZoneInfo(tz)).timestamp())


class TestTimeWindow:
    def test_inside_window_passes(self):
        e = ConstraintRegistry.get("time_window")
        r = e.evaluate(
            TimeWindow(start_hour=9, end_hour=22, timezone="Asia/Seoul"),
            _ctx(requested_at=_at(2026, 5, 6, 14)),
        )
        assert r.passed

    def test_start_boundary_passes(self):
        e = ConstraintRegistry.get("time_window")
        r = e.evaluate(
            TimeWindow(start_hour=9, end_hour=22, timezone="Asia/Seoul"),
            _ctx(requested_at=_at(2026, 5, 6, 9)),
        )
        assert r.passed  # 9:00 is inclusive lower bound

    def test_end_boundary_fails(self):
        e = ConstraintRegistry.get("time_window")
        r = e.evaluate(
            TimeWindow(start_hour=9, end_hour=22, timezone="Asia/Seoul"),
            _ctx(requested_at=_at(2026, 5, 6, 22)),
        )
        assert not r.passed  # end is exclusive

    def test_outside_window_fails(self):
        e = ConstraintRegistry.get("time_window")
        r = e.evaluate(
            TimeWindow(start_hour=9, end_hour=22, timezone="Asia/Seoul"),
            _ctx(requested_at=_at(2026, 5, 6, 3)),
        )
        assert not r.passed

    def test_midnight_crossing_passes(self):
        # 22 -> 6 window, evaluated at 23:00
        e = ConstraintRegistry.get("time_window")
        r = e.evaluate(
            TimeWindow(start_hour=22, end_hour=6, timezone="Asia/Seoul"),
            _ctx(requested_at=_at(2026, 5, 6, 23)),
        )
        assert r.passed


# --- AllowedPlatforms -------------------------------------------------------

class TestAllowedPlatforms:
    def test_allowed_passes(self):
        e = ConstraintRegistry.get("allowed_platforms")
        r = e.evaluate(
            AllowedPlatforms(platforms=["meta_ads", "google_ads"]),
            _ctx(platform="meta_ads"),
        )
        assert r.passed

    def test_not_allowed_fails(self):
        e = ConstraintRegistry.get("allowed_platforms")
        r = e.evaluate(
            AllowedPlatforms(platforms=["meta_ads", "google_ads"]),
            _ctx(platform="naver_searchad"),
        )
        assert not r.passed

    def test_empty_list_blocks_all(self):
        e = ConstraintRegistry.get("allowed_platforms")
        r = e.evaluate(
            AllowedPlatforms(platforms=[]),
            _ctx(platform="meta_ads"),
        )
        assert not r.passed
