"""Declarative, self-validating evaluation plans for RevengeBench Harbor tasks.

The sealed single-container design assigns a strict privilege boundary:

- **learner-authored code** (the agent's policy / probe) must only ever run as
  the unprivileged ``agent`` user — never as root — so it cannot read the
  sealed target, tamper with frozen labels, or escalate;
- the **sealed target** (``/target``) may only be read by root.

Verifiers and multi-phase evaluators encode their steps as an
:class:`EvaluationPlan` and call :meth:`EvaluationPlan.validate` *before*
executing anything. Validation fails closed: a plan that would run learner code
as root (or expose the sealed target to a non-root step) raises
:class:`UnsafeEvaluationError`.

Stdlib only — safe to import inside the lean in-container verifier image and in
unit tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

__all__ = [
    "UnsafeEvaluationError",
    "EvaluationStep",
    "EvaluationPlan",
    "current_user_label",
    "is_root_user",
    "offline_policy_replay_plan",
]


class UnsafeEvaluationError(RuntimeError):
    """Raised when an evaluation plan violates the privilege boundary."""


def is_root_user(user: str | int | None) -> bool:
    """Return ``True`` if *user* denotes the root account (name ``root`` or uid 0)."""
    if user is None:
        return False
    if isinstance(user, int):
        return user == 0
    label = str(user).strip().lower()
    return label in {"root", "0"}


@dataclass(frozen=True)
class EvaluationStep:
    """A single phase of an evaluation, tagged with its privilege contract.

    Attributes
    ----------
    name:
        Short identifier for the step (used in violation messages).
    runs_as:
        The OS user (name or uid) the step's process executes as.
    executes_learner_code:
        Whether learner-authored code runs in this step's process. Such a step
        must never run as root.
    reads_sealed_target:
        Whether the step reads the sealed ``/target``. Only a root step may.
    description:
        Optional human-readable note.
    """

    name: str
    runs_as: str | int
    executes_learner_code: bool = False
    reads_sealed_target: bool = False
    description: str = ""


@dataclass
class EvaluationPlan:
    """An ordered set of :class:`EvaluationStep` with a privilege invariant."""

    name: str
    steps: list[EvaluationStep] = field(default_factory=list)

    def violations(self) -> list[str]:
        """Return a list of privilege-boundary violation messages (empty if safe)."""
        problems: list[str] = []
        for step in self.steps:
            if step.executes_learner_code and is_root_user(step.runs_as):
                problems.append(
                    f"step {step.name!r} executes learner code as root "
                    f"(runs_as={step.runs_as!r})"
                )
            if step.reads_sealed_target and not is_root_user(step.runs_as):
                problems.append(
                    f"step {step.name!r} reads the sealed target as a non-root "
                    f"user (runs_as={step.runs_as!r})"
                )
        return problems

    def validate(self) -> "EvaluationPlan":
        """Raise :class:`UnsafeEvaluationError` if the plan is unsafe; else return self."""
        problems = self.violations()
        if problems:
            raise UnsafeEvaluationError(
                f"unsafe evaluation plan {self.name!r}: " + "; ".join(problems)
            )
        return self


def current_user_label() -> str:
    """Resolve the current effective OS user as a label (name, else uid, else 'unknown')."""
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None:  # non-POSIX (e.g. Windows) — no privilege model here
        return "unknown"
    euid = geteuid()
    try:
        import pwd

        return pwd.getpwuid(euid).pw_name
    except Exception:  # noqa: BLE001 - fall back to the raw uid
        return str(euid)


def offline_policy_replay_plan(runs_as: str | int) -> EvaluationPlan:
    """Plan for offline scoring: replay the learner policy against frozen traces.

    The single step imports and runs the agent's policy, so it must not run as
    root. Frozen target *traces* are already extracted (the sealed target source
    is never touched here), so the step does not read ``/target``.
    """
    return EvaluationPlan(
        name="offline_policy_replay",
        steps=[
            EvaluationStep(
                name="replay_learner_policy",
                runs_as=runs_as,
                executes_learner_code=True,
                reads_sealed_target=False,
                description=(
                    "Import the agent's policy and replay it against the frozen "
                    "target traces to measure mean action distance."
                ),
            )
        ],
    )
