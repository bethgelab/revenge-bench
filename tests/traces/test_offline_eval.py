"""Unit tests for the shared offline scorer (``revenge_bench.traces.offline_eval``).

These cover the pure, container-independent helpers that both the native
tournament and the Harbor verifier delegate to, so the single source of truth
is exercised directly (not only through the end-to-end parity test).
"""

from __future__ import annotations

import math
import json
from pathlib import Path

from revenge_bench.traces.offline_eval import (
    build_trace_summary,
    evaluate_battlesnake_submission,
    evaluate_battlesnake_submission_with_move_provider,
    find_battlesnake_sim_files,
    load_move_function,
    query_move,
    resolve_submission_path,
)


def _write_main(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "main.py"
    p.write_text(body)
    return p


def _battlesnake_turn(turn_num: int, head_x: int, head_y: int, name: str = "target") -> dict:
    snake = {
        "id": "s1",
        "name": name,
        "health": 100,
        "body": [{"x": head_x, "y": head_y}],
        "head": {"x": head_x, "y": head_y},
        "length": 1,
    }
    return {
        "turn": turn_num,
        "board": {"height": 11, "width": 11, "snakes": [snake], "food": [], "hazards": []},
        "you": snake,
    }


def _write_battlesnake_right_trace(path: Path) -> None:
    lines = [
        {"id": "game-1", "ruleset": {"name": "standard"}},
        _battlesnake_turn(0, 0, 5),
        _battlesnake_turn(1, 1, 5),
        _battlesnake_turn(2, 2, 5),
        {"winnerName": "target", "isDraw": False},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")


# --------------------------------------------------------------------------- #
# find_battlesnake_sim_files
# --------------------------------------------------------------------------- #
def test_find_sim_files_flat_layout(tmp_path: Path):
    (tmp_path / "sim_1.jsonl").write_text("{}\n")
    (tmp_path / "sim_0.jsonl").write_text("{}\n")
    files = find_battlesnake_sim_files(tmp_path)
    assert [p.name for p in files] == ["sim_0.jsonl", "sim_1.jsonl"]


def test_find_sim_files_multi_opponent_layout(tmp_path: Path):
    opp = tmp_path / "opp_0"
    opp.mkdir()
    (opp / "sim_0.jsonl").write_text("{}\n")
    files = find_battlesnake_sim_files(tmp_path)
    assert [p.relative_to(tmp_path).as_posix() for p in files] == ["opp_0/sim_0.jsonl"]


def test_find_sim_files_none(tmp_path: Path):
    assert find_battlesnake_sim_files(tmp_path) == []


def test_battlesnake_provider_scoring_matches_inprocess_submission(tmp_path: Path):
    round_dir = tmp_path / "round"
    round_dir.mkdir()
    _write_battlesnake_right_trace(round_dir / "sim_0.jsonl")
    _write_main(tmp_path, "def move(state):\n    return 'right'\n")

    inprocess = evaluate_battlesnake_submission(
        round_dir=round_dir,
        round_num=1,
        target_name="target",
        learner_name="learner",
        learner_code_dir=tmp_path,
    )
    provider = evaluate_battlesnake_submission_with_move_provider(
        round_dir=round_dir,
        round_num=1,
        target_name="target",
        learner_name="learner",
        move_provider=lambda state: "right",
    )

    assert provider == inprocess


def test_battlesnake_none_actions_are_reported_not_scored(tmp_path: Path):
    round_dir = tmp_path / "round"
    round_dir.mkdir()
    _write_battlesnake_right_trace(round_dir / "sim_0.jsonl")

    def move_provider(state: dict):
        if state.get("turn") == 0:
            return None
        return "right"

    summary = evaluate_battlesnake_submission_with_move_provider(
        round_dir=round_dir,
        round_num=1,
        target_name="target",
        learner_name="learner",
        move_provider=move_provider,
        include_diagnostics=True,
    )

    assert summary["expected_actions"] == 2
    assert summary["scored_actions"] == 1
    assert summary["total_actions"] == 1
    assert summary["skipped_none_actions"] == 1
    assert summary["skipped_none_fraction"] == 0.5
    assert summary["mean_distance"] == 0.0
    assert summary["per_simulation"][0]["expected_total"] == 2
    assert summary["per_simulation"][0]["skipped_none"] == 1


# --------------------------------------------------------------------------- #
# resolve_submission_path
# --------------------------------------------------------------------------- #
def test_resolve_submission_direct(tmp_path: Path):
    (tmp_path / "main.py").write_text("x = 1\n")
    sub, code_dir = resolve_submission_path(tmp_path, "main.py")
    assert sub == tmp_path / "main.py"
    assert code_dir == tmp_path


def test_resolve_submission_workspace_subdir(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "main.py").write_text("x = 1\n")
    sub, code_dir = resolve_submission_path(tmp_path, "main.py")
    assert sub == ws / "main.py"
    assert code_dir == ws


def test_resolve_submission_directory_falls_back_to_main(tmp_path: Path):
    # A directory-style submission path with a sibling main.py fallback.
    (tmp_path / "robots").mkdir()
    (tmp_path / "main.py").write_text("x = 1\n")
    sub, code_dir = resolve_submission_path(tmp_path, "robots")
    assert sub == tmp_path / "main.py"


# --------------------------------------------------------------------------- #
# load_move_function
# --------------------------------------------------------------------------- #
def test_load_prefers_move(tmp_path: Path):
    p = _write_main(
        tmp_path,
        "def move(s):\n    return 'up'\n"
        "def choose_move(s):\n    return 'down'\n",
    )
    module, func, kind = load_move_function(p, tmp_path)
    assert module is not None
    assert kind == "move"
    assert func({}) == "up"


def test_load_falls_back_to_choose_move(tmp_path: Path):
    p = _write_main(tmp_path, "def choose_move(s):\n    return 'left'\n")
    _module, func, kind = load_move_function(p, tmp_path)
    assert kind == "choose_move"
    assert func({}) == "left"


def test_load_falls_back_to_robot(tmp_path: Path):
    p = _write_main(tmp_path, "def robot(s, u=None):\n    return {'a': 1}\n")
    _module, func, kind = load_move_function(p, tmp_path)
    assert kind == "robot"


def test_load_no_entrypoint(tmp_path: Path):
    p = _write_main(tmp_path, "def nope(s):\n    return 1\n")
    module, func, kind = load_move_function(p, tmp_path)
    assert module is not None
    assert func is None
    assert kind is None


def test_load_import_error_returns_none(tmp_path: Path):
    p = _write_main(tmp_path, "this is not valid python !!!\n")
    module, func, kind = load_move_function(p, tmp_path)
    assert (module, func, kind) == (None, None, None)


# --------------------------------------------------------------------------- #
# query_move
# --------------------------------------------------------------------------- #
def test_query_move_unwraps_move_dict():
    assert query_move(lambda s: {"move": "up"}, {}) == "up"


def test_query_move_passthrough_non_move_dict():
    action = {"turn": 1, "fire_power": 0.5}
    assert query_move(lambda s: action, {}) == action


def test_query_move_none_func():
    assert query_move(None, {}) is None


def test_query_move_swallows_exception():
    def boom(s):
        raise RuntimeError("nope")

    assert query_move(boom, {}) is None


# --------------------------------------------------------------------------- #
# build_trace_summary
# --------------------------------------------------------------------------- #
def test_build_summary_schema_and_stats():
    per_simulation = [
        {
            "file": "sim_0.jsonl",
            "total": 2,
            "distance_sum": 1.0,
            "mean_distance": 0.5,
            "num_nonzero": 1,
            "expected_total": 3,
            "skipped_none": 1,
        },
    ]
    all_nonzero = [
        {"sim_file": "sim_0.jsonl", "turn": 1, "learner_action": "right", "target_action": "up", "distance": 1.0, "state": {}},
    ]
    summary = build_trace_summary(
        3,
        "BattleSnake",
        "learner",
        "target",
        "offline",
        2,
        1.0,
        per_simulation,
        all_nonzero,
        include_diagnostics=True,
    )
    assert summary["round"] == 3
    assert summary["game"] == "BattleSnake"
    assert summary["learner"] == "learner"
    assert summary["target"] == "target"
    assert summary["evaluation_type"] == "offline"
    assert summary["total_actions"] == 2
    assert summary["scored_actions"] == 2
    assert summary["expected_actions"] == 3
    assert summary["skipped_none_actions"] == 1
    assert summary["skipped_none_fraction"] == 1 / 3
    assert summary["total_distance"] == 1.0
    assert summary["mean_distance"] == 0.5
    assert summary["num_simulations"] == 1
    assert summary["nonzero_distances"] == all_nonzero
    # String actions -> no component_errors block.
    assert "component_errors" not in summary


def test_build_summary_legacy_schema_excludes_diagnostics_by_default():
    per_simulation = [
        {
            "file": "sim_0.jsonl",
            "total": 2,
            "distance_sum": 1.0,
            "mean_distance": 0.5,
            "num_nonzero": 1,
            "expected_total": 3,
            "skipped_none": 1,
        },
    ]
    summary = build_trace_summary(
        3,
        "BattleSnake",
        "learner",
        "target",
        "offline",
        2,
        1.0,
        per_simulation,
        [],
    )

    assert "scored_actions" not in summary
    assert "expected_actions" not in summary
    assert "skipped_none_actions" not in summary
    assert "skipped_none_fraction" not in summary
    assert summary["per_simulation"] == [
        {
            "file": "sim_0.jsonl",
            "total": 2,
            "distance_sum": 1.0,
            "mean_distance": 0.5,
            "num_nonzero": 1,
        },
    ]


def test_build_summary_zero_actions_is_infinite():
    summary = build_trace_summary(0, "BattleSnake", "l", "t", "offline", 0, 0.0, [], [])
    assert math.isinf(summary["mean_distance"])
    assert math.isinf(summary["mean_distance_across_sims"])
    assert summary["distance_std"] == 0.0
    assert summary["distance_se"] == 0.0
