"""
Custom Constraint schema for AP2 Open Mandate (Sprint 1 hands-on).

Notion task: 커스텀 Constraint 스키마 정의
- PRE 4: MaxDailySpend, MaxPerTx, TimeWindow, AllowedPlatforms
- POST 2: MaxCPA, MinCTR
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


# --- Common base -------------------------------------------------------------

class ConstraintBase(BaseModel):
    """All constraints share `type` and `timing`."""
    type: str
    timing: Literal["PRE", "POST"]


class EvaluationContext(BaseModel):
    """
    Per-attempt context passed to every Evaluator.

    PRE evaluators only need the request fields.
    POST evaluators read cumulative_* fields populated from external KPI feed.
    """
    mandate_id: str
    requested_amount_usdc: float
    merchant_id: str
    platform: str
    requested_at: int  # unix seconds

    # Cumulative state (POST + cross-cutting PRE like MaxDailySpend)
    daily_spend_so_far: float = 0.0
    cumulative_cost_usdc: float = 0.0
    cumulative_conversions: int = 0
    cumulative_clicks: int = 0
    cumulative_impressions: int = 0


class EvaluationResult(BaseModel):
    passed: bool
    constraint_type: str
    timing: Literal["PRE", "POST"]
    reason: str | None = None
    layer: Literal["MACRO", "MICRO"] = "MACRO"


# --- PRE constraints ---------------------------------------------------------

class MaxDailySpend(ConstraintBase):
    type: Literal["max_daily_spend"] = "max_daily_spend"
    timing: Literal["PRE"] = "PRE"
    limit_usdc: float = Field(gt=0)


class MaxPerTx(ConstraintBase):
    type: Literal["max_per_tx"] = "max_per_tx"
    timing: Literal["PRE"] = "PRE"
    limit_usdc: float = Field(gt=0)


class TimeWindow(ConstraintBase):
    type: Literal["time_window"] = "time_window"
    timing: Literal["PRE"] = "PRE"
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=0, le=23)
    timezone: str = "Asia/Seoul"


class AllowedPlatforms(ConstraintBase):
    type: Literal["allowed_platforms"] = "allowed_platforms"
    timing: Literal["PRE"] = "PRE"
    platforms: list[str]


# --- POST constraints --------------------------------------------------------

class MaxCPA(ConstraintBase):
    type: Literal["max_cpa"] = "max_cpa"
    timing: Literal["POST"] = "POST"
    threshold_usdc: float = Field(gt=0)
    min_conversions_for_eval: int = 10
    window: Literal["yesterday", "rolling_7d", "campaign_total"] = "rolling_7d"


class MinCTR(ConstraintBase):
    type: Literal["min_ctr"] = "min_ctr"
    timing: Literal["POST"] = "POST"
    threshold_pct: float = Field(gt=0, le=100)
    min_impressions_for_eval: int = 1000
    window: Literal["yesterday", "rolling_7d"] = "rolling_7d"


# --- Discriminated union for serialization -----------------------------------

Constraint = Annotated[
    Union[
        MaxDailySpend,
        MaxPerTx,
        TimeWindow,
        AllowedPlatforms,
        MaxCPA,
        MinCTR,
    ],
    Field(discriminator="type"),
]
