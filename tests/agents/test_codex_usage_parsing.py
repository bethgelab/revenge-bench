"""Tests for codex event parsing + the trajectory ``usage`` / ``events`` fields.

Codex emits ``--json`` mode as one JSON object per line. We parse the
stream into structured events (preserving order, including occasional
non-JSON lines), aggregate ``turn.completed`` usage entries into a
single per-round tally, and persist both ``events`` and ``usage`` on
the trajectory so analysis tooling doesn't have to re-parse anything.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from revenge_bench.agents.codex_agent import (
    CodexInverseStrategyAgent,
    _aggregate_usage,
    _parse_codex_events,
    _parse_codex_usage,
)
from revenge_bench.agents.utils import GameContext


# ----------------------------------------------------------------- #
# Pure parser tests (no agent, no fixtures).
# ----------------------------------------------------------------- #


class TestParseCodexUsage:
    def test_empty_stream_returns_zeros(self):
        result = _parse_codex_usage("")
        assert result == {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
            "turns_completed": 0,
        }

    def test_none_stream_returns_zeros(self):
        # Defensive: real code never passes None, but exercise the path.
        result = _parse_codex_usage("")
        assert result["turns_completed"] == 0

    def test_single_turn_usage(self):
        line = json.dumps({
            "type": "turn.completed",
            "usage": {
                "input_tokens": 10000,
                "cached_input_tokens": 8000,
                "output_tokens": 500,
                "reasoning_output_tokens": 100,
            },
        })
        result = _parse_codex_usage(line + "\n")
        assert result["input_tokens"] == 10000
        assert result["cached_input_tokens"] == 8000
        assert result["output_tokens"] == 500
        assert result["reasoning_output_tokens"] == 100
        assert result["turns_completed"] == 1

    def test_multi_turn_sums_per_round(self):
        l1 = json.dumps({"type": "turn.completed", "usage": {
            "input_tokens": 1000, "cached_input_tokens": 500,
            "output_tokens": 100, "reasoning_output_tokens": 10}})
        l2 = json.dumps({"type": "turn.completed", "usage": {
            "input_tokens": 2000, "cached_input_tokens": 1500,
            "output_tokens": 200, "reasoning_output_tokens": 30}})
        result = _parse_codex_usage(l1 + "\n" + l2 + "\n")
        assert result == {
            "input_tokens": 3000,
            "cached_input_tokens": 2000,
            "output_tokens": 300,
            "reasoning_output_tokens": 40,
            "turns_completed": 2,
        }

    def test_unrelated_lines_ignored(self):
        stream = "\n".join([
            '{"type":"thread.started","thread_id":"abc"}',
            '{"type":"turn.started"}',
            '{"type":"item.completed","item":{"id":"x"}}',
            '{"type":"turn.completed","usage":{"input_tokens":42,'
            '"cached_input_tokens":0,"output_tokens":7,'
            '"reasoning_output_tokens":0}}',
            'plain text line that is not JSON',
            'malformed { json',
        ])
        result = _parse_codex_usage(stream)
        assert result["input_tokens"] == 42
        assert result["output_tokens"] == 7
        assert result["turns_completed"] == 1

    def test_missing_usage_keys_default_to_zero(self):
        # Older codex builds may not emit reasoning_output_tokens.
        line = json.dumps({
            "type": "turn.completed",
            "usage": {"input_tokens": 100, "output_tokens": 5},
        })
        result = _parse_codex_usage(line)
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 5
        assert result["cached_input_tokens"] == 0
        assert result["reasoning_output_tokens"] == 0

    def test_null_usage_value_treated_as_zero(self):
        # Defensive — in case a key is present but null.
        line = json.dumps({
            "type": "turn.completed",
            "usage": {"input_tokens": None, "output_tokens": 5},
        })
        result = _parse_codex_usage(line)
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 5

    def test_timeout_round_no_completed_turns(self):
        """If codex was killed mid-turn, the usage event never fires.
        We return zeros + turns_completed=0 so callers know the tally
        is unavailable, not legitimately zero."""
        stream = "\n".join([
            '{"type":"thread.started"}',
            '{"type":"turn.started"}',
            '{"type":"item.started","item":{"id":"x"}}',
            # No turn.completed — process killed before it could emit.
        ])
        result = _parse_codex_usage(stream)
        assert result["turns_completed"] == 0
        assert result["input_tokens"] == 0


# ----------------------------------------------------------------- #
# Integration: parser output lands in trajectory + agent_stats.
# ----------------------------------------------------------------- #


def _make_agent(tmp_path: Path) -> CodexInverseStrategyAgent:
    env = MagicMock()
    env.execute.return_value = {"output": "deadbeef\n", "returncode": 0}
    log_local = tmp_path / "logs"
    log_local.mkdir()
    config = {
        "name": "learner",
        "agent": "inverse_codex",
        "config": {
            "codex": {
                "command": "codex",
                "model": "gpt-5.4-mini",
                "auth_file": None,
                "max_round_seconds": 60,
            },
        },
    }
    gc = GameContext(
        id="g", log_env=Path("/logs"), log_local=log_local, name="T",
        player_id="learner", prompts={"system_template": "S", "instance_template": "I"},
        round=1, rounds=1, working_dir="/workspace", context_mode="reset",
    )
    return CodexInverseStrategyAgent(config, environment=env, game_context=gc)


class TestUsageInTrajectory:
    def test_usage_field_in_traj_and_agent_stats(self, tmp_path):
        agent = _make_agent(tmp_path)
        usage_payload = {
            "input_tokens": 12345,
            "cached_input_tokens": 10000,
            "output_tokens": 678,
            "reasoning_output_tokens": 42,
            "turns_completed": 1,
        }
        outcome = {
            "exit_status": "ok",
            "submission_status": "submitted",
            "wall_clock_seconds": 5.0,
            "resume_mode": "fresh",
            "usage": usage_payload,
            "last_message": "ok",
            "events": [{"type": "thread.started"}],
        }
        with patch("revenge_bench.agents.codex_agent.copy_to_container"):
            agent._save_round_artifacts(round_num=1, outcome=outcome)

        traj_path = (
            tmp_path / "logs" / "players" / "learner" / "learner_r1.traj.json"
        )
        traj = json.loads(traj_path.read_text())
        assert traj["usage"] == usage_payload

        stats = agent.get_metadata()["agent_stats"][1]
        assert stats["usage"] == usage_payload


class TestEventsField:
    def test_events_persisted_as_structured_list(self, tmp_path):
        """Trajectory should contain the parsed event list, not a raw
        escaped JSONL string. Each entry is a real JSON object that
        readers can index into directly."""
        agent = _make_agent(tmp_path)
        events_payload = [
            {"type": "thread.started", "thread_id": "abc"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {
                "type": "agent_message", "text": "Hello world",
            }},
            {"_kind": "raw_line", "text": "Reading prompt from stdin..."},
        ]
        outcome = {
            "exit_status": "ok",
            "submission_status": "submitted",
            "wall_clock_seconds": 5.0,
            "resume_mode": "fresh",
            "usage": {"input_tokens": 0, "cached_input_tokens": 0,
                      "output_tokens": 0, "reasoning_output_tokens": 0,
                      "turns_completed": 0},
            "last_message": None,
            "events": events_payload,
        }
        with patch("revenge_bench.agents.codex_agent.copy_to_container"):
            agent._save_round_artifacts(round_num=1, outcome=outcome)

        traj_path = (
            tmp_path / "logs" / "players" / "learner" / "learner_r1.traj.json"
        )
        traj = json.loads(traj_path.read_text())
        # No raw stdout / tail field on the trajectory.
        assert "stdout" not in traj
        assert "stdout_tail" not in traj
        assert traj["events"] == events_payload
        # Confirm the on-disk file uses real nested JSON, not an escaped
        # string. A JSON-encoded list of dicts contains "[{" but no
        # backslash-escaped quotes for those inner objects.
        raw = traj_path.read_text()
        assert '"events": [' in raw
        assert '\\"thread.started\\"' not in raw  # not escaped


class TestParseCodexEvents:
    def test_empty_stream(self):
        assert _parse_codex_events("") == []

    def test_single_json_line(self):
        ev = _parse_codex_events('{"type":"turn.started"}\n')
        assert ev == [{"type": "turn.started"}]

    def test_mixed_lines_preserve_order(self):
        stream = (
            "Reading prompt from stdin...\n"
            '{"type":"thread.started","thread_id":"x"}\n'
            '{"type":"turn.started"}\n'
        )
        ev = _parse_codex_events(stream)
        assert ev == [
            {"_kind": "raw_line", "text": "Reading prompt from stdin..."},
            {"type": "thread.started", "thread_id": "x"},
            {"type": "turn.started"},
        ]

    def test_malformed_json_line_kept_as_raw(self):
        ev = _parse_codex_events('{"broken: missing-quote\n')
        assert len(ev) == 1
        assert ev[0]["_kind"] == "raw_line"
        assert "broken" in ev[0]["text"]

    def test_blank_lines_dropped(self):
        ev = _parse_codex_events('{"type":"a"}\n\n   \n{"type":"b"}\n')
        assert ev == [{"type": "a"}, {"type": "b"}]


class TestAggregateUsageFromEvents:
    def test_aggregates_turn_completed_events(self):
        events = [
            {"type": "turn.started"},
            {"type": "turn.completed", "usage": {
                "input_tokens": 100, "cached_input_tokens": 50,
                "output_tokens": 10, "reasoning_output_tokens": 1}},
            {"type": "turn.started"},
            {"type": "turn.completed", "usage": {
                "input_tokens": 200, "cached_input_tokens": 150,
                "output_tokens": 20, "reasoning_output_tokens": 3}},
        ]
        usage = _aggregate_usage(events)
        assert usage == {
            "input_tokens": 300,
            "cached_input_tokens": 200,
            "output_tokens": 30,
            "reasoning_output_tokens": 4,
            "turns_completed": 2,
        }

    def test_no_turn_completed_returns_zeros(self):
        usage = _aggregate_usage([{"type": "turn.started"}])
        assert usage["turns_completed"] == 0
        assert usage["input_tokens"] == 0

    def test_legacy_wrapper_still_works(self):
        # Public _parse_codex_usage(stdout) is kept as a convenience.
        stream = '{"type":"turn.completed","usage":{"input_tokens":42}}\n'
        usage = _parse_codex_usage(stream)
        assert usage["input_tokens"] == 42
        assert usage["turns_completed"] == 1
