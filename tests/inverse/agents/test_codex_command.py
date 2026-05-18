"""Unit tests for the Codex `exec` command builders.

Pure-function tests — no container, no subprocess, no filesystem.
"""

import pytest

from revenge_bench.agents.codex_agent import (
    _build_codex_resume_command,
    build_codex_command,
)


class TestBuildCodexCommand:
    def test_minimal_required_args(self):
        cmd = build_codex_command(
            codex_config={"model": "gpt-5-mini"},
            output_path="/codex_home/last_message_r1.txt",
        )
        assert cmd[0] == "codex"
        assert cmd[1] == "exec"
        # required flags
        assert "--cd" in cmd and cmd[cmd.index("--cd") + 1] == "/workspace"
        assert "--json" in cmd
        assert "--color" in cmd and cmd[cmd.index("--color") + 1] == "never"
        assert "--model" in cmd and cmd[cmd.index("--model") + 1] == "gpt-5-mini"
        assert "--output-last-message" in cmd
        assert (
            cmd[cmd.index("--output-last-message") + 1]
            == "/codex_home/last_message_r1.txt"
        )
        # default sandbox
        assert "--sandbox" in cmd
        assert cmd[cmd.index("--sandbox") + 1] == "workspace-write"
        # default skip_git_repo_check is True
        assert "--skip-git-repo-check" in cmd
        # ephemeral defaults to False
        assert "--ephemeral" not in cmd

    def test_custom_command_name(self):
        cmd = build_codex_command(
            codex_config={"command": "/usr/local/bin/codex", "model": "gpt-5-mini"},
            output_path="/tmp/last.txt",
        )
        assert cmd[0] == "/usr/local/bin/codex"

    def test_skip_git_repo_check_disabled(self):
        cmd = build_codex_command(
            codex_config={"model": "m", "skip_git_repo_check": False},
            output_path="/tmp/x",
        )
        assert "--skip-git-repo-check" not in cmd

    def test_ephemeral_enabled(self):
        cmd = build_codex_command(
            codex_config={"model": "m", "ephemeral": True},
            output_path="/tmp/x",
        )
        assert "--ephemeral" in cmd

    def test_profile_passthrough(self):
        cmd = build_codex_command(
            codex_config={"model": "m", "profile": "ci-bench"},
            output_path="/tmp/x",
        )
        idx = cmd.index("--profile")
        assert cmd[idx + 1] == "ci-bench"

    def test_profile_null_is_skipped(self):
        cmd = build_codex_command(
            codex_config={"model": "m", "profile": None},
            output_path="/tmp/x",
        )
        assert "--profile" not in cmd

    def test_config_overrides_string_value(self):
        cmd = build_codex_command(
            codex_config={
                "model": "m",
                "config_overrides": {"model_reasoning_effort": "low"},
            },
            output_path="/tmp/x",
        )
        # find the -c pair
        c_indexes = [i for i, x in enumerate(cmd) if x == "-c"]
        assert len(c_indexes) == 1
        assert cmd[c_indexes[0] + 1] == "model_reasoning_effort=low"

    def test_config_overrides_bool_lowercased(self):
        cmd = build_codex_command(
            codex_config={
                "model": "m",
                "config_overrides": {"some_flag": True, "other_flag": False},
            },
            output_path="/tmp/x",
        )
        joined = " ".join(cmd)
        assert "some_flag=true" in joined
        assert "other_flag=false" in joined

    def test_config_overrides_int_value(self):
        cmd = build_codex_command(
            codex_config={
                "model": "m",
                "config_overrides": {"tool_output_token_limit": 3000},
            },
            output_path="/tmp/x",
        )
        joined = " ".join(cmd)
        assert "tool_output_token_limit=3000" in joined

    def test_extra_args_appended(self):
        cmd = build_codex_command(
            codex_config={"model": "m"},
            output_path="/tmp/x",
            extra_args=["resume", "--last"],
        )
        assert cmd[-2:] == ["resume", "--last"]

    def test_missing_model_raises(self):
        with pytest.raises(ValueError, match="model"):
            build_codex_command(codex_config={}, output_path="/tmp/x")

    def test_custom_sandbox(self):
        cmd = build_codex_command(
            codex_config={"model": "m", "sandbox": "read-only"},
            output_path="/tmp/x",
        )
        assert cmd[cmd.index("--sandbox") + 1] == "read-only"


class TestBuildCodexResumeCommand:
    """`codex exec resume` accepts a strict subset of `codex exec` flags;
    session-state args are inherited from the original session and would
    be rejected here."""

    def test_resume_has_resume_subcommand_after_exec(self):
        cmd = _build_codex_resume_command(
            codex_config={"model": "m"}, output_path="/tmp/x"
        )
        assert cmd[:4] == ["codex", "exec", "resume", "--last"]

    def test_resume_passes_through_model_and_json(self):
        cmd = _build_codex_resume_command(
            codex_config={"model": "gpt-5.4-mini"}, output_path="/tmp/x"
        )
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "gpt-5.4-mini"
        assert "--json" in cmd
        assert "--output-last-message" in cmd
        assert cmd[cmd.index("--output-last-message") + 1] == "/tmp/x"

    def test_resume_does_not_include_session_state_flags(self):
        """`--cd`, `--sandbox`, `--color`, `--profile` are inherited
        from the parent session and rejected by `codex exec resume`."""
        cmd = _build_codex_resume_command(
            codex_config={
                "model": "m",
                "sandbox": "workspace-write",
                "profile": "ci-bench",
            },
            output_path="/tmp/x",
        )
        assert "--cd" not in cmd
        assert "--sandbox" not in cmd
        assert "--color" not in cmd
        assert "--profile" not in cmd

    def test_resume_bypasses_sandbox_when_danger_full_access(self):
        """`resume` doesn't propagate the parent session's sandbox; the
        only resume-compatible way to skip bwrap (which fails inside
        Docker) is `--dangerously-bypass-approvals-and-sandbox`."""
        cmd = _build_codex_resume_command(
            codex_config={"model": "m", "sandbox": "danger-full-access"},
            output_path="/tmp/x",
        )
        assert "--dangerously-bypass-approvals-and-sandbox" in cmd

    def test_resume_no_bypass_for_other_sandboxes(self):
        cmd = _build_codex_resume_command(
            codex_config={"model": "m", "sandbox": "workspace-write"},
            output_path="/tmp/x",
        )
        assert "--dangerously-bypass-approvals-and-sandbox" not in cmd

    def test_resume_passes_skip_git_repo_check(self):
        cmd = _build_codex_resume_command(
            codex_config={"model": "m", "skip_git_repo_check": True},
            output_path="/tmp/x",
        )
        assert "--skip-git-repo-check" in cmd

    def test_resume_passes_config_overrides(self):
        cmd = _build_codex_resume_command(
            codex_config={
                "model": "m",
                "config_overrides": {"model_reasoning_effort": "low"},
            },
            output_path="/tmp/x",
        )
        c_idx = cmd.index("-c")
        assert cmd[c_idx + 1] == "model_reasoning_effort=low"

    def test_resume_missing_model_raises(self):
        with pytest.raises(ValueError, match="model"):
            _build_codex_resume_command(codex_config={}, output_path="/tmp/x")
