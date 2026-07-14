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

The offline (trace-replay) scoring used by Harbor lives under
:mod:`revenge_bench.harbor.traces`. It intentionally duplicates the native
behavior behind Harbor-specific parity tests so the main benchmark pipeline can
remain unchanged.
"""

from __future__ import annotations

__all__ = ["evaluators"]
