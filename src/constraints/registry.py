"""
ConstraintRegistry - factory pattern.

Notion task: 커스텀 Constraint Evaluator 구현
- 팩토리 패턴으로 각 타입별 Evaluator 등록
"""
from __future__ import annotations

from typing import Protocol

from .schema import ConstraintBase, EvaluationContext, EvaluationResult


class Evaluator(Protocol):
    def evaluate(
        self, c: ConstraintBase, ctx: EvaluationContext
    ) -> EvaluationResult: ...


class ConstraintRegistry:
    _evaluators: dict[str, Evaluator] = {}

    @classmethod
    def register(cls, type_: str):
        def deco(eval_cls):
            cls._evaluators[type_] = eval_cls()
            return eval_cls

        return deco

    @classmethod
    def get(cls, type_: str) -> Evaluator:
        if type_ not in cls._evaluators:
            raise KeyError(f"Unknown constraint type: {type_}")
        return cls._evaluators[type_]

    @classmethod
    def known_types(cls) -> list[str]:
        return list(cls._evaluators.keys())


def evaluate_pre(
    constraints: list[ConstraintBase], ctx: EvaluationContext
) -> list[EvaluationResult]:
    return [
        ConstraintRegistry.get(c.type).evaluate(c, ctx)
        for c in constraints
        if c.timing == "PRE"
    ]


def evaluate_post(
    constraints: list[ConstraintBase], ctx: EvaluationContext
) -> list[EvaluationResult]:
    return [
        ConstraintRegistry.get(c.type).evaluate(c, ctx)
        for c in constraints
        if c.timing == "POST"
    ]


def all_passed(results: list[EvaluationResult]) -> bool:
    return all(r.passed for r in results)


def first_failure(results: list[EvaluationResult]) -> EvaluationResult | None:
    for r in results:
        if not r.passed:
            return r
    return None
