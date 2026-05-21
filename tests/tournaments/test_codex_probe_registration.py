"""Probe registration relaxed from isinstance() to set_probe_callback hasattr.

Verifies the interventionist tournament wires probes for any learner that
exposes `set_probe_callback`, not just `InverseStrategyAgent`. This is the
single line that lets `CodexInverseStrategyAgent` participate in
interventionist runs without the tournament importing Codex types.
"""

from unittest.mock import MagicMock


def test_register_probe_callback_for_codex_like_learner():
    """A learner that quacks like an inverse-strategy agent (has
    set_probe_callback) should receive the probe callback even if it's
    not a subclass of InverseStrategyAgent."""
    from revenge_bench.tournaments.inverse_strategy_interventionist import (
        InverseStrategyInterventionistTournament,
    )

    # Build a fake tournament shell so we can call the registration block.
    # We don't need a fully constructed tournament — just enough for the
    # `if hasattr(self.learner_agent, "set_probe_callback")` line to see
    # the right object.
    fake_self = MagicMock()
    fake_self.max_probes_per_round = 5
    fake_self.sims_per_probe = 3
    fake_self.logger = MagicMock()

    # Codex-like learner: not an InverseStrategyAgent subclass, but exposes
    # the protocol method.
    codex_like_learner = MagicMock(spec=["set_probe_callback"])
    fake_self.learner_agent = codex_like_learner
    fake_self._run_inline_probe = lambda: "{}"
    fake_self._seed_probe = lambda: None
    fake_self.run_edit_phase = lambda r: None
    fake_self.round_probe_traces = []
    fake_self.current_round = None

    # Call the bound `_run_edit_phase_with_probing` directly on the fake.
    InverseStrategyInterventionistTournament._run_edit_phase_with_probing(fake_self, 1)

    codex_like_learner.set_probe_callback.assert_called_once()
    kwargs = codex_like_learner.set_probe_callback.call_args.kwargs
    assert kwargs["max_probes"] == 5
    assert callable(kwargs["callback"])


def test_register_skipped_when_protocol_absent():
    """A learner without set_probe_callback should NOT have probe wiring
    attempted — the interventionist tournament must degrade silently for
    non-probing learners."""
    from revenge_bench.tournaments.inverse_strategy_interventionist import (
        InverseStrategyInterventionistTournament,
    )

    fake_self = MagicMock()
    fake_self.max_probes_per_round = 5
    fake_self.sims_per_probe = 3
    fake_self.logger = MagicMock()

    bare_learner = object()  # no set_probe_callback
    fake_self.learner_agent = bare_learner
    fake_self._run_inline_probe = lambda: "{}"
    fake_self._seed_probe = lambda: None
    fake_self.run_edit_phase = lambda r: None
    fake_self.round_probe_traces = []
    fake_self.current_round = None

    # Should not raise; the hasattr guard skips the call.
    InverseStrategyInterventionistTournament._run_edit_phase_with_probing(fake_self, 1)
