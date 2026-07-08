from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS = REPO_ROOT / "harbor" / "tasks"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_battlesnake_trace_generator_matches_normal_per_sim_player_shuffle():
    text = (
        TASKS
        / "battlesnake-gpt5-9aa3-v0"
        / "environment"
        / "generate_round_traces.py"
    ).read_text()
    assert 'players = [\n                ("target", target_port),' in text
    assert "random.shuffle(players)" in text
    assert "for name, port in players:" in text
    assert "check=False" in text
    assert "if proc.returncode != 0:" in text
    assert "empty/missing trace" in text


def test_robocode_trace_generator_uses_shuffled_alias_mapping():
    text = (
        TASKS
        / "robocode-gpt5-9aa3-v0"
        / "environment"
        / "generate_round_traces.py"
    ).read_text()
    assert 'players = [("target", TARGET), ("opponent", opponent)]' in text
    assert "random.shuffle(players)" in text
    assert "pkg_to_agent[pkg] = role" in text
    assert '{"p0": "target", "p1": "opponent"}' not in text
    assert '"target_identity": "per-opponent _pkg_to_agent.json"' in text


def test_halite_and_robotrumble_use_runtime_shuffle_not_seeded_shortcut():
    for task in ("halite-gpt5-9aa3-v0", "robotrumble-gpt5-9aa3-v0"):
        text = (TASKS / task / "environment" / "generate_round_traces.py").read_text()
        assert "random.shuffle(players)" in text
        assert "random.Random(seed + opp_idx).shuffle(players)" not in text


def test_halite_compile_submission_rejects_multiple_top_level_mains(tmp_path: Path):
    module = _load_module(
        TASKS / "halite-gpt5-9aa3-v0" / "environment" / "halite_common.py",
        "halite_common_for_test",
    )
    submission = tmp_path / "submission"
    submission.mkdir()
    (submission / "main.c").write_text("int main(void) { return 0; }\n")
    (submission / "main.cpp").write_text("int main() { return 0; }\n")

    with pytest.raises(RuntimeError, match="Exactly one main"):
        module.compile_submission(submission)


def test_run_probe_does_not_accept_env_controlled_privileged_paths():
    forbidden = (
        "TARGET_DIR:-",
        "BATTLESNAKE_SERVER:-",
        "BATTLESNAKE_BIN:-",
        "PROBE_PARSER:-",
        "PROBE_ARENA:-",
        "BOARD_W:-",
        "BOARD_H:-",
        "os.environ",
        "getenv",
        "environ.get",
    )
    for task in (
        "battlesnake-gpt5-9aa3-v0",
        "halite-gpt5-9aa3-v0",
        "huskybench-gpt5-9aa3-v0",
        "robocode-gpt5-9aa3-v0",
        "robotrumble-gpt5-9aa3-v0",
    ):
        environment = TASKS / task / "environment"
        for path in (environment / "run_probe", environment / "run_probe_impl.py"):
            if path.exists():
                text = path.read_text()
                for token in forbidden:
                    assert token not in text, f"{path} contains {token}"
