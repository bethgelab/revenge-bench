"""Lifecycle tests for InverseStrategyAgent (init_session / run_round / finalize)."""

from pathlib import Path
from unittest.mock import MagicMock

from revenge_bench.agents.minisweagent import InverseStrategyAgent
from revenge_bench.agents.utils import GameContext


def _make_player(tmp_path, model_outputs):
    env = MagicMock()
    env.execute.return_value = {"output": "ok\n", "returncode": 0}
    env.get_template_vars.return_value = {}
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    config = {
        "name": "learner",
        "config": {
            "model": {
                "model_class": "minisweagent.models.test_models.DeterministicModel",
                "outputs": model_outputs,
            },
            "agent": {
                "system_template": "SYS",
                "instance_template": "TASK",
                "action_observation_template": "<output>{{output.output}}</output>",
                "format_error_template": "bad",
                "timeout_template": "to",
                "step_limit": 30,
                "cost_limit": 1.0,
            },
        },
    }
    game_context = GameContext(
        id="g", log_env=Path("/logs"), log_local=log_dir,
        name="Test", player_id="learner", prompts={}, round=1, rounds=3,
        working_dir="/work",
    )
    p = InverseStrategyAgent(config, environment=env, game_context=game_context)
    return p


class TestLifecycle:
    def test_init_session_constructs_inner_agent_with_pinned_prompts(self, tmp_path):
        p = _make_player(tmp_path, model_outputs=[])
        p.init_session()
        assert p.agent is not None
        assert len(p.agent.messages) == 2  # system + instance
        # subsequent init is a no-op
        p.init_session()
        assert len(p.agent.messages) == 2

    def test_run_round_extends_step_limit(self, tmp_path):
        outputs = [
            "r1a\n```bash\necho 1\n```",
            "r1b\n```bash\necho 2\n```",
            "r2a\n```bash\necho 3\n```",
            "r2b\n```bash\necho 4\n```",
        ]
        p = _make_player(tmp_path, model_outputs=outputs)
        p.init_session()
        p.run_round(round_num=1, transition_summary=None,
                    step_increment=2, cost_increment=10.0)
        n_after_r1 = len(p.agent.messages)
        p.run_round(round_num=2,
                    transition_summary={"distance": 0.5, "previous_distance": 0.7,
                                        "mismatches": 5, "submission_status": "ok"},
                    step_increment=2, cost_increment=10.0)
        # round 2 must add at least the round-transition message + activity
        assert len(p.agent.messages) > n_after_r1
        pinned = [m for m in p.agent.messages if m.get("pinned")]
        assert len(pinned) == 1
        assert "Round 1 evaluation complete" in pinned[0]["content"]


class TestProbeCountResetAcrossRounds:
    def test_probe_count_resets_each_round(self, tmp_path):
        """Without per-round reset, max_probes_per_round would only apply to round 1."""
        outputs = ["r1\n```bash\necho 1\n```", "r2\n```bash\necho 2\n```"]
        p = _make_player(tmp_path, model_outputs=outputs)
        p.init_session()
        # Simulate that round 1 used up all probes
        p.run_round(round_num=1, transition_summary=None,
                    step_increment=1, cost_increment=10.0)
        p.agent.probe_count = 5  # pretend round 1 maxed out
        p._max_probes = 5
        p.agent.max_probes = 5
        # Round 2 should reset probe_count
        p.run_round(round_num=2,
                    transition_summary={"distance": 0.5, "previous_distance": 0.7,
                                        "mismatches": 5, "submission_status": "ok"},
                    step_increment=1, cost_increment=10.0)
        # The reset happens at the start of run_round, so after returning,
        # probe_count is back to 0 (since this round didn't probe).
        assert p.agent.probe_count == 0
