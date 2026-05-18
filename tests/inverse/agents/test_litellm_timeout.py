"""Regression tests: model_kwargs.timeout must flow through to litellm.completion()
and a hung HTTP call must raise within the configured timeout (not hang forever).

Context: BEFORE this fix, OpenRouter-routed runs would hang for 6+ hours on
half-closed (CLOSE_WAIT) sockets because no read timeout was configured. After
this fix, every config in configs/inverse/openrouter_pool/ has timeout: 300 in
model_kwargs, and litellm raises litellm.exceptions.Timeout (which the upstream
tenacity decorator retries since Timeout is NOT a subclass of
litellm.exceptions.APIError).
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from minisweagent.models.litellm_model import LitellmModel


def test_timeout_kwarg_reaches_litellm_completion():
    """LitellmModel must forward model_kwargs['timeout'] to litellm.completion()."""
    model = LitellmModel(
        model_name="openrouter/dummy/model",
        model_kwargs={"timeout": 7},
    )
    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        # Minimal response shape for LitellmModel.query post-processing.
        class _Choice:
            class message:  # noqa: N801
                content = "ok"
        class _Resp:
            choices = [_Choice()]
            def model_dump(self):
                return {}
        return _Resp()

    with patch("litellm.completion", side_effect=fake_completion):
        # cost_calculator may complain — the model swallows that into cost=0
        # when cost_tracking="ignore_errors", but our default fixture doesn't
        # set that. Patch cost_calculator to silence it.
        with patch("litellm.cost_calculator.completion_cost", return_value=0.01):
            model.query([{"role": "user", "content": "hi"}])

    assert captured.get("timeout") == 7, (
        f"timeout did not reach litellm.completion; got kwargs={list(captured)}"
    )


def test_hung_completion_raises_within_timeout():
    """A litellm.completion() that takes longer than `timeout` must raise
    litellm.exceptions.Timeout, not return.

    We simulate the hang by monkeypatching litellm.completion to sleep+raise
    the way litellm itself would on an httpx read timeout. This proves the
    contract LitellmModel relies on; the real hang is enforced inside
    litellm/httpx and is not exercised here.

    We bypass upstream's tenacity decorator (which would otherwise retry up
    to MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT times — that env var is read at
    decorator-definition time, so changing it from a test body has no
    effect). Tenacity exposes the un-decorated function as
    `_query.retry.wrapped_function`. We call that directly.
    """
    import litellm

    model = LitellmModel(
        model_name="openrouter/dummy/model",
        model_kwargs={"timeout": 1, "num_retries": 0},
    )

    def slow_completion(**kwargs):
        # Honour the timeout the caller passed, then raise the real exception.
        time.sleep(kwargs.get("timeout", 0))
        raise litellm.exceptions.Timeout(
            message="simulated read timeout",
            model=kwargs.get("model", ""),
            llm_provider="openai",
        )

    # Resolve the un-decorated _query. Different tenacity versions expose
    # the wrapped function differently:
    #   - Tenacity ~8.x: `.retry.wrapped_function`
    #   - On this codebase's tenacity (Retrying object exposes no
    #     `wrapped_function` attribute), the bound method exposes
    #     `__wrapped__` and `inspect.unwrap()` resolves it.
    # Try `__wrapped__` first (works here), then `inspect.unwrap()`, then
    # the older `.retry.wrapped_function` path as a fallback.
    import inspect as _inspect

    raw_query = getattr(model._query, "__wrapped__", None)
    if raw_query is None:
        unwrapped = _inspect.unwrap(model._query)
        if unwrapped is not model._query:
            raw_query = unwrapped
    if raw_query is None:
        retry_obj = getattr(model._query, "retry", None)
        raw_query = getattr(retry_obj, "wrapped_function", None) if retry_obj else None
    assert raw_query is not None, (
        "could not locate un-decorated _query — tenacity API changed?"
    )

    start = time.monotonic()
    with patch("litellm.completion", side_effect=slow_completion):
        with pytest.raises(litellm.exceptions.Timeout):
            raw_query(model, [{"role": "user", "content": "hi"}])
    elapsed = time.monotonic() - start
    # 1s timeout + small overhead; should finish well under 5s.
    assert elapsed < 5.0, f"call took {elapsed:.1f}s, suggesting timeout was not honoured"


def test_litellm_timeout_is_not_litellm_api_error_subclass():
    """If this test fails on a LiteLLM upgrade, the upstream tenacity
    decorator at minisweagent.models.litellm_model._query (which excludes
    litellm.exceptions.APIError) will start swallowing Timeout instead of
    retrying. Update the upstream exclusion handling or pin LiteLLM."""
    from litellm.exceptions import Timeout, APIError
    assert not issubclass(Timeout, APIError), (
        "litellm.exceptions.Timeout has become a subclass of "
        "litellm.exceptions.APIError. Upstream's tenacity retry decorator "
        "excludes APIError, so Timeout will no longer be retried — and the "
        "OpenRouter CLOSE_WAIT fix will silently regress. "
        "See docs/superpowers/plans/2026-04-30-openrouter-close-wait-timeout-fix.md"
    )
