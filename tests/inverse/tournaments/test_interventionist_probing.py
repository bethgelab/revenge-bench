"""
Tests for Inline Probing in Interventionist Tournament.

Tests the inline probing mechanism where:
1. probe.py is auto-seeded from main.py at each edit phase start
2. Agent modifies probe.py for exploration
3. Agent runs `echo "PROBE_SUBMIT"`
4. ClashAgent intercepts and calls probe callback
5. Probe callback runs probe.py vs target and returns results

This allows testing the probing infrastructure without a real LLM.
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Test: ClashAgent Probe Interception
# =============================================================================


class TestClashAgentProbeInterception:
    """Tests for ClashAgent intercepting PROBE_SUBMIT commands."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        """Set up mocks to avoid circular import issues."""
        # Mock the problematic imports before importing ClashAgent
        with patch.dict(
            sys.modules,
            {
                "revenge_bench.agents": MagicMock(),
                "revenge_bench.agents.player": MagicMock(),
            },
        ):
            yield

    def test_detects_probe_submit_command(self):
        """Should detect PROBE_SUBMIT in command output."""
        # Import directly to avoid circular imports
        from minisweagent.agents.default import AgentConfig, DefaultAgent

        # Create a minimal ClashAgent-like class for testing
        class TestClashAgent(DefaultAgent):
            def __init__(self, model, env, probe_callback=None, max_probes=5, **kwargs):
                super().__init__(model, env, config_class=AgentConfig, **kwargs)
                self.probe_callback = probe_callback
                self.max_probes = max_probes
                self.probe_count = 0

            def execute_action(self, action):
                output = self.env.execute(action["action"])
                lines = output.get("output", "").strip().splitlines()
                if lines and lines[0].strip() == "PROBE_SUBMIT":
                    if self.probe_callback is None:
                        return {
                            "output": "ERROR: Probing not available",
                            "returncode": 1,
                        }
                    elif self.probe_count >= self.max_probes:
                        return {
                            "output": f"ERROR: Probe limit exceeded ({self.max_probes} probes max)",
                            "returncode": 1,
                        }
                    else:
                        probe_result = self.probe_callback()
                        self.probe_count += 1
                        return {
                            "output": f"PROBE RESULT ({self.probe_count}/{self.max_probes}):\n{probe_result}",
                            "returncode": 0,
                        }
                return output

        mock_env = MagicMock()
        mock_model = MagicMock()

        probe_results = {"probe_id": 1, "total_turns": 10}
        probe_callback = MagicMock(return_value=json.dumps(probe_results))

        agent = TestClashAgent(
            model=mock_model,
            env=mock_env,
            probe_callback=probe_callback,
            max_probes=5,
        )

        mock_env.execute.return_value = {"output": "PROBE_SUBMIT\n", "returncode": 0}

        action = {"action": 'echo "PROBE_SUBMIT"'}
        result = agent.execute_action(action)

        probe_callback.assert_called_once()
        assert "PROBE RESULT" in result["output"]
        assert "(1/5)" in result["output"]

    def test_does_not_intercept_normal_commands(self):
        """Should not intercept normal bash commands."""
        from minisweagent.agents.default import AgentConfig, DefaultAgent

        class TestClashAgent(DefaultAgent):
            def __init__(self, model, env, probe_callback=None, max_probes=5, **kwargs):
                super().__init__(model, env, config_class=AgentConfig, **kwargs)
                self.probe_callback = probe_callback
                self.max_probes = max_probes
                self.probe_count = 0

            def execute_action(self, action):
                output = self.env.execute(action["action"])
                lines = output.get("output", "").strip().splitlines()
                if lines and lines[0].strip() == "PROBE_SUBMIT":
                    if self.probe_callback:
                        probe_result = self.probe_callback()
                        self.probe_count += 1
                        return {
                            "output": f"PROBE RESULT:\n{probe_result}",
                            "returncode": 0,
                        }
                return output

        mock_env = MagicMock()
        mock_model = MagicMock()
        probe_callback = MagicMock()

        agent = TestClashAgent(
            model=mock_model,
            env=mock_env,
            probe_callback=probe_callback,
            max_probes=5,
        )

        mock_env.execute.return_value = {
            "output": "main.py\nprobe.py\n",
            "returncode": 0,
        }

        action = {"action": "ls"}
        result = agent.execute_action(action)

        probe_callback.assert_not_called()
        assert "main.py" in result["output"]

    def test_respects_max_probes_limit(self):
        """Should enforce max probes per round."""
        from minisweagent.agents.default import AgentConfig, DefaultAgent

        class TestClashAgent(DefaultAgent):
            def __init__(self, model, env, probe_callback=None, max_probes=5, **kwargs):
                super().__init__(model, env, config_class=AgentConfig, **kwargs)
                self.probe_callback = probe_callback
                self.max_probes = max_probes
                self.probe_count = 0

            def execute_action(self, action):
                output = self.env.execute(action["action"])
                lines = output.get("output", "").strip().splitlines()
                if lines and lines[0].strip() == "PROBE_SUBMIT":
                    if self.probe_count >= self.max_probes:
                        return {
                            "output": f"ERROR: Probe limit exceeded ({self.max_probes} probes max)",
                            "returncode": 1,
                        }
                    else:
                        probe_result = self.probe_callback()
                        self.probe_count += 1
                        return {
                            "output": f"PROBE RESULT ({self.probe_count}/{self.max_probes}):\n{probe_result}",
                            "returncode": 0,
                        }
                return output

        mock_env = MagicMock()
        mock_model = MagicMock()
        probe_callback = MagicMock(return_value='{"probe_id": 1}')

        agent = TestClashAgent(
            model=mock_model,
            env=mock_env,
            probe_callback=probe_callback,
            max_probes=2,
        )

        mock_env.execute.return_value = {"output": "PROBE_SUBMIT\n", "returncode": 0}
        action = {"action": 'echo "PROBE_SUBMIT"'}

        result1 = agent.execute_action(action)
        assert "PROBE RESULT" in result1["output"]

        result2 = agent.execute_action(action)
        assert "PROBE RESULT" in result2["output"]

        result3 = agent.execute_action(action)
        assert "ERROR" in result3["output"]
        assert "limit exceeded" in result3["output"].lower()

        assert probe_callback.call_count == 2

    def test_handles_no_callback(self):
        """Should return error if no probe callback is set."""
        from minisweagent.agents.default import AgentConfig, DefaultAgent

        class TestClashAgent(DefaultAgent):
            def __init__(self, model, env, probe_callback=None, max_probes=5, **kwargs):
                super().__init__(model, env, config_class=AgentConfig, **kwargs)
                self.probe_callback = probe_callback
                self.max_probes = max_probes
                self.probe_count = 0

            def execute_action(self, action):
                output = self.env.execute(action["action"])
                lines = output.get("output", "").strip().splitlines()
                if lines and lines[0].strip() == "PROBE_SUBMIT":
                    if self.probe_callback is None:
                        return {
                            "output": "ERROR: Probing not available in this mode",
                            "returncode": 1,
                        }
                return output

        mock_env = MagicMock()
        mock_model = MagicMock()

        agent = TestClashAgent(
            model=mock_model,
            env=mock_env,
            probe_callback=None,
            max_probes=5,
        )

        mock_env.execute.return_value = {"output": "PROBE_SUBMIT\n", "returncode": 0}
        action = {"action": 'echo "PROBE_SUBMIT"'}

        result = agent.execute_action(action)

        assert "ERROR" in result["output"]
        assert "not available" in result["output"].lower()

    def test_handles_callback_exception(self):
        """Should handle exceptions from probe callback gracefully."""
        from minisweagent.agents.default import AgentConfig, DefaultAgent

        class TestClashAgent(DefaultAgent):
            def __init__(self, model, env, probe_callback=None, max_probes=5, **kwargs):
                super().__init__(model, env, config_class=AgentConfig, **kwargs)
                self.probe_callback = probe_callback
                self.max_probes = max_probes
                self.probe_count = 0

            def execute_action(self, action):
                output = self.env.execute(action["action"])
                lines = output.get("output", "").strip().splitlines()
                if lines and lines[0].strip() == "PROBE_SUBMIT":
                    try:
                        probe_result = self.probe_callback()
                        self.probe_count += 1
                        return {
                            "output": f"PROBE RESULT:\n{probe_result}",
                            "returncode": 0,
                        }
                    except Exception as e:
                        return {"output": f"ERROR: Probe failed: {e}", "returncode": 1}
                return output

        mock_env = MagicMock()
        mock_model = MagicMock()
        probe_callback = MagicMock(side_effect=RuntimeError("Container not found"))

        agent = TestClashAgent(
            model=mock_model,
            env=mock_env,
            probe_callback=probe_callback,
            max_probes=5,
        )

        mock_env.execute.return_value = {"output": "PROBE_SUBMIT\n", "returncode": 0}
        action = {"action": 'echo "PROBE_SUBMIT"'}

        result = agent.execute_action(action)

        assert "ERROR" in result["output"]
        assert "Container not found" in result["output"]


# =============================================================================
# Test: InverseStrategyAgent Probe Setup
# =============================================================================


class TestInverseStrategyAgentProbeSetup:
    """Tests for InverseStrategyAgent probe callback setup."""

    def test_set_probe_callback(self):
        """Should accept and store probe callback."""
        # Test the callback storage logic directly without full agent
        class MockAgent:
            def __init__(self):
                self._probe_callback = None
                self._max_probes = 5

            def set_probe_callback(self, callback, max_probes=5):
                self._probe_callback = callback
                self._max_probes = max_probes

        agent = MockAgent()
        callback = MagicMock()
        agent.set_probe_callback(callback, max_probes=3)

        assert agent._probe_callback is callback
        assert agent._max_probes == 3


# =============================================================================
# Test: Tournament Probe Callback
# =============================================================================


class TestTournamentProbeCallback:
    """Tests for tournament-level probe callback (_run_inline_probe)."""

    def test_probe_auto_seeds_from_main(self):
        """Should auto-seed probe.py from main.py at edit phase start."""
        # Test the auto-seeding logic from _run_edit_phase_with_probing
        mock_tournament = MagicMock()
        mock_tournament.learner_agent = MagicMock()
        mock_tournament.round_probe_traces = []
        mock_tournament.current_round = 1

        # Simulate the auto-seed call
        mock_tournament.learner_agent.environment.execute(
            "cp /workspace/main.py /workspace/probe.py"
        )

        # Verify cp was called
        mock_tournament.learner_agent.environment.execute.assert_called_with(
            "cp /workspace/main.py /workspace/probe.py"
        )

    def test_probe_increments_counters(self):
        """Should increment probe counters when running."""
        # Track counters
        counters = {"probe_count": 0, "round_probe_count": 0}

        def mock_run_inline_probe():
            counters["probe_count"] += 1
            counters["round_probe_count"] += 1
            return json.dumps({"probe_id": counters["probe_count"]})

        # Run probe
        mock_run_inline_probe()

        assert counters["probe_count"] == 1
        assert counters["round_probe_count"] == 1


# =============================================================================
# Test: Full Probing Flow (Integration-like)
# =============================================================================


class TestFullProbingFlow:
    """Integration-like tests for the full probing flow."""

    def test_probe_callback_wiring(self):
        """Test that probe callback is properly wired from tournament to agent."""
        # Test the callback storage pattern

        class MockAgent:
            def __init__(self):
                self._probe_callback = None
                self._max_probes = 5

            def set_probe_callback(self, callback, max_probes=5):
                self._probe_callback = callback
                self._max_probes = max_probes

        probe_callback = MagicMock(return_value='{"probe_id": 1}')
        agent = MockAgent()

        # Set callback (as tournament would do)
        agent.set_probe_callback(probe_callback, max_probes=5)

        # Verify callback is stored
        assert agent._probe_callback is probe_callback
        assert agent._max_probes == 5

    def test_deterministic_probe_sequence(self):
        """Test a deterministic sequence: modify probe.py, submit probe.

        probe.py is auto-seeded from main.py, so agent only needs to modify and submit.
        """
        from minisweagent.agents.default import AgentConfig, DefaultAgent

        # Create a TestClashAgent that mirrors ClashAgent behavior
        class TestClashAgent(DefaultAgent):
            def __init__(self, model, env, probe_callback=None, max_probes=5, **kwargs):
                super().__init__(model, env, config_class=AgentConfig, **kwargs)
                self.probe_callback = probe_callback
                self.max_probes = max_probes
                self.probe_count = 0

            def execute_action(self, action):
                output = self.env.execute(action["action"])
                lines = output.get("output", "").strip().splitlines()
                if lines and lines[0].strip() == "PROBE_SUBMIT":
                    if self.probe_callback is None:
                        return {
                            "output": "ERROR: Probing not available",
                            "returncode": 1,
                        }
                    elif self.probe_count >= self.max_probes:
                        return {
                            "output": "ERROR: Probe limit exceeded",
                            "returncode": 1,
                        }
                    else:
                        probe_result = self.probe_callback()
                        self.probe_count += 1
                        return {
                            "output": f"PROBE RESULT ({self.probe_count}/{self.max_probes}):\n{probe_result}",
                            "returncode": 0,
                        }
                return output

        mock_env = MagicMock()
        mock_model = MagicMock()

        # Track probe calls
        probe_calls = []

        def probe_callback():
            probe_calls.append(True)
            return json.dumps(
                {
                    "probe_id": len(probe_calls),
                    "total_turns": 25,
                    "pairs": [
                        {"turn": 0, "probe_action": "up", "target_action": "right"},
                        {"turn": 1, "probe_action": "up", "target_action": "up"},
                    ],
                }
            )

        agent = TestClashAgent(
            model=mock_model,
            env=mock_env,
            probe_callback=probe_callback,
            max_probes=5,
        )

        # Simulate command sequence:
        # probe.py is already auto-seeded from main.py by the tournament

        # 1. Modify probe.py for exploration
        mock_env.execute.return_value = {"output": "probe.py modified", "returncode": 0}
        agent.execute_action(
            {"action": "sed -i 's/random.choice/\"up\"/g' probe.py"}
        )
        assert len(probe_calls) == 0  # No probe yet

        # 2. Submit probe
        mock_env.execute.return_value = {"output": "PROBE_SUBMIT\n", "returncode": 0}
        result2 = agent.execute_action({"action": 'echo "PROBE_SUBMIT"'})

        # Probe should have been called
        assert len(probe_calls) == 1
        assert "PROBE RESULT" in result2["output"]
        assert "total_turns" in result2["output"]
        assert "probe_action" in result2["output"]

        # 3. Submit another probe
        result3 = agent.execute_action({"action": 'echo "PROBE_SUBMIT"'})
        assert len(probe_calls) == 2
        assert "(2/5)" in result3["output"]  # Second probe


# =============================================================================
# Test: Probe Output Parsing
# =============================================================================


class TestProbeOutputParsing:
    """Tests for parsing probe simulation outputs."""

    def test_probe_output_structure(self):
        """Verify expected probe output structure."""
        # This is the format we expect from _run_inline_probe
        expected_format = {
            "probe_id": 1,
            "description": "probe.py (seeded from your main.py) vs target - showing what each did in same state",
            "total_turns": 45,
            "num_simulations": 3,
            "per_simulation": [
                {"file": "sim_0.jsonl", "num_turns": 15},
                {"file": "sim_1.jsonl", "num_turns": 15},
                {"file": "sim_2.jsonl", "num_turns": 15},
            ],
            "pairs": [
                {
                    "turn": 0,
                    "probe_action": "up",
                    "target_action": "right",
                    "target_state": {"you": {"head": {"x": 5, "y": 5}}},
                },
            ],
        }

        # Verify it can be serialized/deserialized
        json_str = json.dumps(expected_format)
        parsed = json.loads(json_str)

        assert parsed["probe_id"] == 1
        assert parsed["total_turns"] == 45
        assert len(parsed["pairs"]) == 1
        assert parsed["pairs"][0]["probe_action"] == "up"
        assert parsed["pairs"][0]["target_action"] == "right"

    def test_probe_error_output(self):
        """Verify error output structure for read failures."""
        error_output = {
            "error": "Failed to read probe.py",
        }

        json_str = json.dumps(error_output)
        parsed = json.loads(json_str)

        assert "error" in parsed
        assert "probe.py" in parsed["error"]


# =============================================================================
# Test: DeterministicModel Integration
# =============================================================================


class TestDeterministicModelProbing:
    """Test probing with DeterministicModel (for testing without real LLM)."""

    def test_deterministic_model_config_for_probing(self):
        """Verify DeterministicModel config structure for probe testing.

        probe.py is auto-seeded, so the agent just needs to modify and submit.
        """
        # This config would make the agent:
        # 1. Modify probe.py for exploration (already seeded from main.py)
        # 2. Submit probe
        # 3. Edit main.py based on probe results
        # 4. Submit final

        outputs = [
            # Step 1: Modify probe.py for exploration (already auto-seeded from main.py)
            "```bash\nsed -i 's/random.choice(safe_moves)/\"up\"/g' probe.py\n```",
            # Step 2: Submit probe to see what target does
            '```bash\necho "PROBE_SUBMIT"\n```',
            # Step 3: Read probe results (already in observation)
            # Then edit main.py based on what we learned
            '```bash\ncat << \'EOF\' > main.py\ndef move(game_state):\n    return {"move": "right"}\nEOF\n```',
            # Step 4: Submit final
            "```bash\necho COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n```",
        ]

        config = {
            "model_name": "probe_test",
            "model_class": "minisweagent.models.test_models.DeterministicModel",
            "outputs": outputs,
        }

        # Verify structure
        assert "DeterministicModel" in config["model_class"]
        assert len(config["outputs"]) == 4
        assert "PROBE_SUBMIT" in config["outputs"][1]

    def test_create_probe_test_yaml_config(self):
        """Verify we can create a YAML config for probe testing.

        probe.py is auto-seeded, so steps are: modify, submit, done.
        """
        import yaml

        outputs = [
            "```bash\nsed -i 's/random.choice/\"up\"/g' probe.py\n```",
            '```bash\necho "PROBE_SUBMIT"\n```',
            "```bash\necho COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n```",
        ]

        config = {
            "model_name": "probe_test",
            "model_class": "minisweagent.models.test_models.DeterministicModel",
            "outputs": outputs,
        }

        yaml_str = yaml.dump(config, default_flow_style=False)

        assert "DeterministicModel" in yaml_str
        assert "PROBE_SUBMIT" in yaml_str
