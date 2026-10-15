"""Unit tests for the pure evaluation-plan privilege model (``evaluators.py``)."""

from __future__ import annotations

import pytest

from revenge_bench.harbor.evaluators import (
    EvaluationPlan,
    EvaluationStep,
    UnsafeEvaluationError,
    current_user_label,
    is_root_user,
    offline_policy_replay_plan,
)


def test_is_root_user():
    assert is_root_user("root")
    assert is_root_user("ROOT")
    assert is_root_user("0")
    assert is_root_user(0)
    assert not is_root_user("agent")
    assert not is_root_user("nobody")
    assert not is_root_user(1000)
    assert not is_root_user(None)


def test_learner_code_as_root_is_rejected():
    plan = EvaluationPlan(
        name="bad",
        steps=[
            EvaluationStep(
                name="replay", runs_as="root", executes_learner_code=True
            )
        ],
    )
    assert plan.violations()
    with pytest.raises(UnsafeEvaluationError, match="executes learner code as root"):
        plan.validate()


def test_learner_code_as_nonroot_is_allowed():
    plan = EvaluationPlan(
        name="ok",
        steps=[
            EvaluationStep(
                name="replay", runs_as="agent", executes_learner_code=True
            )
        ],
    )
    assert plan.violations() == []
    assert plan.validate() is plan


def test_sealed_target_read_requires_root():
    unsafe = EvaluationPlan(
        name="leak",
        steps=[
            EvaluationStep(
                name="compare", runs_as="agent", reads_sealed_target=True
            )
        ],
    )
    with pytest.raises(UnsafeEvaluationError, match="reads the sealed target"):
        unsafe.validate()

    safe = EvaluationPlan(
        name="oracle",
        steps=[
            EvaluationStep(
                name="compare", runs_as="root", reads_sealed_target=True
            )
        ],
    )
    assert safe.validate() is safe


def test_multiple_violations_reported():
    plan = EvaluationPlan(
        name="twowrong",
        steps=[
            EvaluationStep(name="a", runs_as="root", executes_learner_code=True),
            EvaluationStep(name="b", runs_as="agent", reads_sealed_target=True),
        ],
    )
    problems = plan.violations()
    assert len(problems) == 2


def test_offline_policy_replay_plan_is_safe_when_unprivileged():
    plan = offline_policy_replay_plan("agent")
    assert plan.name == "offline_policy_replay"
    assert plan.validate() is plan
    step = plan.steps[0]
    assert step.executes_learner_code is True
    assert step.reads_sealed_target is False


def test_offline_policy_replay_plan_rejects_root():
    with pytest.raises(UnsafeEvaluationError):
        offline_policy_replay_plan("root").validate()
    with pytest.raises(UnsafeEvaluationError):
        offline_policy_replay_plan(0).validate()


def test_current_user_label_returns_str():
    label = current_user_label()
    assert isinstance(label, str)
    assert label
