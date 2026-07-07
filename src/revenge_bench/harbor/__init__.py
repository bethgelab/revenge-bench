"""RevengeBench Harbor integration (additive).

This subpackage packages RevengeBench's inverse-strategy evaluation as
`Harbor <https://github.com/harbor-framework/harbor>`_ tasks, following the
single-container, Unix-user-sealed design proven in the AgenticPIC repo.

Nothing in the core ``revenge_bench`` package imports from here; the Harbor
feature is entirely opt-in. The deployable Harbor task assets (Dockerfiles,
``task.toml``, ``run_probe`` oracle scripts, verifier ``tests/``) live in the
top-level ``harbor/`` directory of the repository, mirroring how MLS-Bench
keeps its Harbor packaging self-contained.

Modules
-------
evaluators
    Declarative, self-validating :class:`EvaluationPlan` codifying the
    privilege boundary (learner code never runs as root; only root reads the
    sealed target). Stdlib only.
agent
    ``HarborRevengeAgent`` — an optional Harbor-compatible agent bridge for
    mini-swe-agent parity runs. The deployable tasks themselves are normal
    Harbor artifacts and keep probe budget enforcement inside ``sudo
    run_probe``. Imported lazily (it pulls in the ``harbor`` and
    ``minisweagent`` frameworks) so ``import revenge_bench.harbor`` stays
    dependency-light.

The offline (trace-replay) scoring itself is **not** duplicated here: both the
native tournament and the in-container verifier import the single source of
truth at :mod:`revenge_bench.traces.offline_eval`.
"""

from __future__ import annotations

__all__ = ["evaluators", "HarborRevengeAgent"]


def __getattr__(name: str):
    """Lazily expose the Harbor agent bridge without importing frameworks eagerly."""
    if name == "HarborRevengeAgent":
        from revenge_bench.harbor.agent import HarborRevengeAgent

        return HarborRevengeAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
