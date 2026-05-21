"""Tests for the credential-redaction defence layer.

Codex's shell tool can read its own ``auth.json`` (we documented why).
As a last line of defence, the agent extracts token-shaped values from
the host auth file at init time and scrubs them out of any captured
codex output before persisting to the trajectory JSON.

Verifies:
- top-level keys captured for audit (logged + put in metadata),
- recursive value collection (nested dicts/lists),
- 12-char threshold filters out short identifiers,
- ``last_message`` and ``events`` are redacted recursively in the
  trajectory (events being a list of nested dicts),
- log message records the key names (but not values),
- ``auth_file: null`` skips the whole mechanism cleanly,
- malformed auth.json does not crash agent init.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from revenge_bench.agents.codex_agent import CodexInverseStrategyAgent
from revenge_bench.agents.utils import GameContext


def _make_agent(tmp_path: Path, *, auth_file: str | None | object = "__default__") -> CodexInverseStrategyAgent:
    """Build a Codex agent. ``auth_file`` semantics:

    - ``"__default__"`` (sentinel): omit `auth_file` from config →
      agent uses the resolver default ``~/.codex/auth.json``.
    - ``None``: explicit ``auth_file: null`` → redaction disabled.
    - ``str``: explicit path → redaction reads from there.
    """
    env = MagicMock()
    env.execute.return_value = {"output": "deadbeef\n", "returncode": 0}
    log_local = tmp_path / "logs"
    log_local.mkdir()

    codex_block: dict = {"command": "codex", "model": "gpt-5-mini"}
    if auth_file != "__default__":
        codex_block["auth_file"] = auth_file

    config = {
        "name": "learner",
        "agent": "inverse_codex",
        "config": {"codex": codex_block},
    }
    gc = GameContext(
        id="g",
        log_env=Path("/logs"),
        log_local=log_local,
        name="Test",
        player_id="learner",
        prompts={"system_template": "SYS", "instance_template": "INST"},
        round=1,
        rounds=2,
        working_dir="/workspace",
        context_mode="reset",
    )
    return CodexInverseStrategyAgent(config, environment=env, game_context=gc)


def _write_auth(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "auth.json"
    p.write_text(json.dumps(payload))
    return p


class TestKeyAndValueExtraction:
    def test_simple_flat_dict(self, tmp_path):
        auth = _write_auth(tmp_path, {
            "OPENAI_API_KEY": "sk-1234567890abcdefABCDEF",
            "kind": "openai",  # short identifier — should NOT be redacted
        })
        agent = _make_agent(tmp_path, auth_file=str(auth))
        assert sorted(agent._auth_key_names) == ["OPENAI_API_KEY", "kind"]
        # The long token shows up in the redaction list; the short
        # identifier doesn't.
        assert "sk-1234567890abcdefABCDEF" in agent._auth_redactable
        assert "openai" not in agent._auth_redactable

    def test_nested_values(self, tmp_path):
        auth = _write_auth(tmp_path, {
            "tokens": {
                "access_token": "ya29.A0ARrdaM_long_oauth_access_token_value",
                "refresh_token": "1//04abcdef-refresh-very-long-string",
            },
            "scopes": ["openid", "email", "profile"],
        })
        agent = _make_agent(tmp_path, auth_file=str(auth))
        # Nested string values are picked up.
        assert "ya29.A0ARrdaM_long_oauth_access_token_value" in agent._auth_redactable
        assert "1//04abcdef-refresh-very-long-string" in agent._auth_redactable
        # Short scope strings are below threshold.
        assert "openid" not in agent._auth_redactable
        assert "email" not in agent._auth_redactable

    def test_redaction_list_sorted_longest_first(self, tmp_path):
        auth = _write_auth(tmp_path, {
            "short_secret": "abcdefghijkl",  # exactly 12, included
            "long_secret":  "abcdefghijkl-EXTENDED-ZZZ",
        })
        agent = _make_agent(tmp_path, auth_file=str(auth))
        # Longer string sorts first so the full secret is redacted
        # before its shorter prefix.
        assert agent._auth_redactable[0] == "abcdefghijkl-EXTENDED-ZZZ"

    def test_threshold_excludes_short_values(self, tmp_path):
        auth = _write_auth(tmp_path, {
            "type": "oauth",        # 5 chars
            "version": "1.0",       # 3 chars
            "id_token_short": "x" * 11,    # 11 chars — below threshold
            "id_token_okay":  "x" * 12,    # 12 chars — at threshold, included
        })
        agent = _make_agent(tmp_path, auth_file=str(auth))
        assert "oauth" not in agent._auth_redactable
        assert "1.0" not in agent._auth_redactable
        assert "x" * 11 not in agent._auth_redactable
        assert "x" * 12 in agent._auth_redactable


class TestRedactionApplied:
    def test_events_and_last_message_redacted(self, tmp_path):
        secret = "sk-this-is-a-real-looking-test-token-xyz"
        auth = _write_auth(tmp_path, {"OPENAI_API_KEY": secret})
        agent = _make_agent(tmp_path, auth_file=str(auth))

        outcome = {
            "exit_status": "submitted",
            "submission_status": None,
            "wall_clock_seconds": 1.0,
            "resume_mode": "fresh",
            "usage": {"input_tokens": 0, "cached_input_tokens": 0,
                      "output_tokens": 0, "reasoning_output_tokens": 0,
                      "turns_completed": 0},
            "last_message": f"Final message contains {secret} oops",
            # Mix of nested dicts and a raw_line — redaction has to
            # walk recursively into both kinds of entries.
            "events": [
                {"type": "thread.started", "thread_id": "abc"},
                {"type": "item.completed", "item": {
                    "type": "command_execution",
                    "command": f"cat /tmp/{secret}/data",
                    "aggregated_output": f"contents include {secret}",
                }},
                {"_kind": "raw_line", "text": f"plaintext leak: {secret}"},
            ],
        }
        with patch("revenge_bench.agents.codex_agent.copy_to_container"):
            agent._save_round_artifacts(round_num=1, outcome=outcome)

        traj_path = (
            tmp_path / "logs" / "players" / "learner" / "learner_r1.traj.json"
        )
        # The secret never lands on disk anywhere in the trajectory.
        assert secret not in traj_path.read_text()
        traj = json.loads(traj_path.read_text())
        assert "[REDACTED]" in traj["last_message"]
        # All three event entries had the secret; all should be redacted.
        events = traj["events"]
        assert "[REDACTED]" in events[1]["item"]["command"]
        assert "[REDACTED]" in events[1]["item"]["aggregated_output"]
        assert "[REDACTED]" in events[2]["text"]
        # Surrounding fields preserved.
        assert events[0] == {"type": "thread.started", "thread_id": "abc"}
        assert events[1]["type"] == "item.completed"

    def test_no_redaction_when_auth_disabled(self, tmp_path):
        agent = _make_agent(tmp_path, auth_file=None)
        outcome = {
            "exit_status": "submitted",
            "submission_status": None,
            "wall_clock_seconds": 1.0,
            "resume_mode": "fresh",
            "usage": {"input_tokens": 0, "cached_input_tokens": 0,
                      "output_tokens": 0, "reasoning_output_tokens": 0,
                      "turns_completed": 0},
            "last_message": "no secrets here",
            "events": [
                {"type": "turn.started"},
                {"_kind": "raw_line", "text": "still no secrets"},
            ],
        }
        with patch("revenge_bench.agents.codex_agent.copy_to_container"):
            agent._save_round_artifacts(round_num=1, outcome=outcome)
        traj = json.loads(
            (tmp_path / "logs" / "players" / "learner" / "learner_r1.traj.json").read_text()
        )
        assert traj["last_message"] == "no secrets here"
        assert traj["events"] == [
            {"type": "turn.started"},
            {"_kind": "raw_line", "text": "still no secrets"},
        ]

    def test_redact_walks_nested_structures(self, tmp_path):
        secret = "x" * 30
        auth = _write_auth(tmp_path, {"k": secret})
        agent = _make_agent(tmp_path, auth_file=str(auth))
        nested = {
            "outer": {
                "inner_list": [secret, "ok", {"deep": secret}],
                "tuple_like": (secret, "ok"),  # tuples are leaf — left alone
            },
            "scalar": 42,  # non-string scalars untouched
        }
        # Tuples aren't redacted (they're a non-recursive type per spec).
        # The nested string list and dict entries are.
        out = agent._redact(nested)
        assert out["outer"]["inner_list"] == ["[REDACTED]", "ok", {"deep": "[REDACTED]"}]
        assert out["scalar"] == 42

    def test_redaction_no_op_on_none_and_empty(self, tmp_path):
        agent = _make_agent(tmp_path, auth_file=None)
        assert agent._redact(None) is None
        assert agent._redact("") == ""
        assert agent._redact([]) == []
        assert agent._redact({}) == {}


class TestAuditTrail:
    def test_keys_logged_on_init(self, tmp_path, caplog):
        secret = "x" * 30
        auth = _write_auth(tmp_path, {"OPENAI_API_KEY": secret, "tokens": {}})
        with caplog.at_level("INFO"):
            agent = _make_agent(tmp_path, auth_file=str(auth))
        log_text = caplog.text
        # Key names appear in the log.
        assert "OPENAI_API_KEY" in log_text
        assert "tokens" in log_text
        # The actual secret value does NOT.
        assert secret not in log_text

    def test_keys_recorded_in_metadata(self, tmp_path):
        auth = _write_auth(tmp_path, {"alpha": "x" * 30, "beta": "y" * 30})
        agent = _make_agent(tmp_path, auth_file=str(auth))
        observed = agent.get_metadata()["inverse_strategy"]["auth_keys_observed"]
        assert sorted(observed) == ["alpha", "beta"]

    def test_metadata_omitted_when_no_auth(self, tmp_path):
        agent = _make_agent(tmp_path, auth_file=None)
        # The key is absent (rather than empty list) when redaction is
        # not configured at all — clearer signal in the saved metadata.
        assert "auth_keys_observed" not in agent.get_metadata()["inverse_strategy"]


class TestEdgeCases:
    def test_malformed_auth_does_not_crash(self, tmp_path, caplog):
        bad = tmp_path / "auth.json"
        bad.write_text("not valid json {{{")
        with caplog.at_level("WARNING"):
            agent = _make_agent(tmp_path, auth_file=str(bad))
        assert agent._auth_key_names == []
        assert agent._auth_redactable == []
        assert "Could not parse" in caplog.text

    def test_non_dict_auth_skipped(self, tmp_path):
        # Some auth flows might write a bare string or list; collect
        # values but emit no key names.
        bad = tmp_path / "auth.json"
        bad.write_text(json.dumps(["sometokenvalue1234", "anothertoken5678"]))
        agent = _make_agent(tmp_path, auth_file=str(bad))
        # No top-level keys to log.
        assert agent._auth_key_names == []
        # But values are still collected for redaction.
        assert "sometokenvalue1234" in agent._auth_redactable

    def test_explicit_path_missing_does_not_crash_init(self, tmp_path, monkeypatch):
        """Explicit-path missing raises in `_copy_host_auth_file` (when
        the agent runs), but auth-secret loading at __init__ should
        silently no-op so the agent can at least be constructed for
        introspection / dry runs."""
        missing = tmp_path / "definitely_missing.json"
        # __init__ does not call _copy_host_auth_file; it only calls
        # _load_auth_secrets which returns ([], []) on missing file.
        agent = _make_agent(tmp_path, auth_file=str(missing))
        assert agent._auth_key_names == []
        assert agent._auth_redactable == []
