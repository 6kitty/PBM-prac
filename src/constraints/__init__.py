"""Custom constraint package."""
from . import evaluators  # noqa: F401  (registers all 6 types)
from .registry import (
    ConstraintRegistry,
    Evaluator,
    all_passed,
    evaluate_post,
    evaluate_pre,
    first_failure,
)
from .schema import (
    AllowedPlatforms,
    Constraint,
    ConstraintBase,
    EvaluationContext,
    EvaluationResult,
    MaxCPA,
    MaxDailySpend,
    MaxPerTx,
    MinCTR,
    TimeWindow,
)

__all__ = [
    "AllowedPlatforms",
    "Constraint",
    "ConstraintBase",
    "ConstraintRegistry",
    "EvaluationContext",
    "EvaluationResult",
    "Evaluator",
    "MaxCPA",
    "MaxDailySpend",
    "MaxPerTx",
    "MinCTR",
    "TimeWindow",
    "all_passed",
    "evaluate_post",
    "evaluate_pre",
    "first_failure",
]
