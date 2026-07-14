"""Harbor-only offline policy-replay scoring for inverse-strategy tasks.

This module mirrors the native tournament scoring behavior without making the
native tournament import Harbor code. Harbor verifiers install ``revenge_bench``
inside the task image and call these helpers directly; parity tests compare the
result with the native path on the same synthetic traces.

The heavy per-game Harbor parser helpers (``actions_distance`` /
``extract_state_action_pairs`` / ``ACTION_COMPONENTS`` ...) are imported lazily
inside the functions that need them so importing this module stays light.
"""

from __future__ import annotations

import importlib.util
import json
import statistics
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "find_battlesnake_sim_files",
    "find_halite_sim_files",
    "find_robotrumble_sim_files",
    "find_robocode_sim_files",
    "find_huskybench_sim_files",
    "robotrumble_target_team_for_sim",
    "robocode_parser_target_name_for_sim",
    "resolve_submission_path",
    "load_move_function",
    "load_huskybench_bot",
    "query_move",
    "score_battlesnake_simulations",
    "score_battlesnake_simulations_with_provider",
    "score_halite_simulations_with_provider",
    "score_robotrumble_simulations_with_provider",
    "score_robocode_simulations_with_provider",
    "score_huskybench_simulations_with_provider",
    "evaluate_battlesnake_submission_with_move_provider",
    "evaluate_halite_submission_with_action_provider",
    "evaluate_robotrumble_submission_with_action_provider",
    "evaluate_robocode_submission_with_move_provider",
    "evaluate_huskybench_submission_with_action_provider",
    "make_huskybench_bot_action_provider",
    "make_robotrumble_js_action_provider",
    "compute_component_errors",
    "build_trace_summary",
    "evaluate_battlesnake_submission",
]


# --------------------------------------------------------------------------- #
# Sim-file discovery
# --------------------------------------------------------------------------- #
def find_battlesnake_sim_files(round_dir: Path) -> list[Path]:
    """Return the sorted BattleSnake ``sim_*.jsonl`` trace files under *round_dir*.

    Mirrors ``InverseStrategyTournament._process_battlesnake_traces``: prefers a
    flat ``sim_*.jsonl`` layout, falling back to the multi-opponent
    ``opp_*/sim_*.jsonl`` layout.
    """
    sim_files = sorted(round_dir.glob("sim_*.jsonl"))
    if not sim_files:
        sim_files = sorted(round_dir.glob("opp_*/sim_*.jsonl"))
    return sim_files


def find_halite_sim_files(round_dir: Path) -> list[Path]:
    """Return the sorted Halite I ``.hlt`` traces under *round_dir*.

    Mirrors ``InverseStrategyTournament._process_halite_traces``: prefers a
    flat round directory, falling back to the multi-opponent ``opp_*`` layout.
    """
    sim_files = sorted(round_dir.glob("*.hlt"))
    if not sim_files:
        sim_files = sorted(round_dir.glob("opp_*/*.hlt"))
    return sim_files


def find_robotrumble_sim_files(round_dir: Path) -> list[Path]:
    """Return the sorted RobotRumble ``sim_*.json`` traces under *round_dir*.

    Mirrors ``InverseStrategyTournament._process_robotrumble_traces``: prefers
    a flat round directory, falling back to the multi-opponent ``opp_*`` layout.
    """
    sim_files = sorted(round_dir.glob("sim_*.json"))
    if not sim_files:
        sim_files = sorted(round_dir.glob("opp_*/sim_*.json"))
    return sim_files


def find_robocode_sim_files(round_dir: Path) -> list[Path]:
    """Return the sorted RoboCode ``record_*.xml`` traces under *round_dir*.

    Mirrors ``InverseStrategyTournament._process_robocode_traces``: prefers a
    flat round directory, falling back to the multi-opponent ``opp_*`` layout.
    """
    sim_files = sorted(round_dir.glob("record_*.xml"))
    if not sim_files:
        sim_files = sorted(round_dir.glob("opp_*/record_*.xml"))
    return sim_files


def find_huskybench_sim_files(round_dir: Path) -> list[Path]:
    """Return sorted HuskyBench ``game_log_*.json`` files under *round_dir*.

    Mirrors ``InverseStrategyTournament._process_huskybench_traces``: prefers a
    flat round directory, falling back to the multi-opponent ``opp_*`` layout.
    """
    sim_files = sorted(round_dir.glob("game_log_*.json"))
    if not sim_files:
        sim_files = sorted(round_dir.glob("opp_*/game_log_*.json"))
    return sim_files


def robocode_parser_target_name_for_sim(
    sim_file: Path,
    target_name: str,
    *,
    fallback_parser_target_name: str | None = None,
) -> str:
    """Return the RoboCode package alias assigned to *target_name* for a trace.

    Normal multi-opponent runs can shuffle the target/opponent order separately
    for each opponent.  RoboCode XML stores short package aliases (``p0``,
    ``p1``), so the parser target must be resolved from the mapping adjacent to
    each trace file rather than once per whole round.
    """

    for path in (sim_file.parent / "_pkg_to_agent.json", sim_file.parent.parent / "_pkg_to_agent.json"):
        if not path.exists():
            continue
        pkg_to_agent = json.loads(path.read_text())
        agent_to_pkg = {v: k for k, v in pkg_to_agent.items()}
        return agent_to_pkg.get(
            target_name, fallback_parser_target_name or target_name
        )
    return fallback_parser_target_name or target_name


# --------------------------------------------------------------------------- #
# Learner-module loading + querying
# --------------------------------------------------------------------------- #
def resolve_submission_path(
    learner_code_dir: Path, submission: str
) -> tuple[Path, Path]:
    """Resolve the learner submission ``.py`` file and its code directory.

    Mirrors the path resolution inside
    ``InverseStrategyTournament._load_learner_module``:

    * ``copy_from_container`` places ``/workspace`` under a ``workspace/``
      subdirectory, so prefer that when present;
    * directory-based submissions (or a missing file) fall back to ``main.py``
      in the workspace root.

    Returns ``(submission_py, code_dir)``.
    """
    workspace_dir = learner_code_dir / "workspace"
    if workspace_dir.exists():
        submission_py = workspace_dir / submission
        code_dir = submission_py.parent
    else:
        submission_py = learner_code_dir / submission
        code_dir = submission_py.parent

    if submission_py.is_dir() or not submission_py.exists():
        fallback = (
            workspace_dir if workspace_dir.exists() else learner_code_dir
        ) / "main.py"
        if fallback.exists():
            submission_py = fallback
            code_dir = fallback.parent

    return submission_py, code_dir


def load_move_function(
    submission_py: Path, code_dir: Path
) -> tuple[Any | None, Callable | None, str | None]:
    """Import *submission_py* and return ``(module, move_func, entry_kind)``.

    ``entry_kind`` is one of ``"move"``, ``"choose_move"``, ``"robot"`` or
    ``None`` (module imported but no recognised entrypoint). On import failure
    returns ``(None, None, None)`` (and prints the traceback, as the tournament
    does).

    Mirrors the import + entrypoint-selection logic of
    ``InverseStrategyTournament._load_learner_module``.
    """
    try:
        # Add the learner's code directory to path for any relative imports.
        if str(code_dir) not in sys.path:
            sys.path.insert(0, str(code_dir))

        spec = importlib.util.spec_from_file_location("learner_main", submission_py)
        if spec is None or spec.loader is None:
            return None, None, None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:
        traceback.print_exc()
        return None, None, None

    # Accept move(), choose_move() or robot() (RobotRumble API), in that order.
    if hasattr(module, "move"):
        return module, module.move, "move"
    if hasattr(module, "choose_move"):
        return module, module.choose_move, "choose_move"
    if hasattr(module, "robot"):
        return module, module.robot, "robot"
    return module, None, None


def load_huskybench_bot(
    submission_py: Path,
    code_dir: Path,
) -> tuple[Any | None, Any | None, Any | None, str | None]:
    """Load a HuskyBench Bot subclass from ``client/player.py``.

    Returns ``(module, bot, RoundStateClient, error)``. The loading and class
    selection intentionally mirror the native tournament's historical
    ``_process_huskybench_traces`` implementation.
    """
    import inspect

    try:
        if str(code_dir) not in sys.path:
            sys.path.insert(0, str(code_dir))

        spec = importlib.util.spec_from_file_location(
            "learner_huskybench", submission_py
        )
        if spec is None or spec.loader is None:
            return None, None, None, f"Could not load spec for {submission_py}"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:  # noqa: BLE001 - match native tolerant loading
        traceback.print_exc()
        return None, None, None, f"Failed to load module: {e}"

    bot_class = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name, None)
        if (
            inspect.isclass(attr)
            and hasattr(attr, "get_action")
            and attr_name != "Bot"
        ):
            bot_class = attr
            break

    if bot_class is None:
        return module, None, None, "No Bot subclass with get_action() found in submission"

    RoundStateClient = getattr(module, "RoundStateClient", None)
    if RoundStateClient is None:
        return module, None, None, "RoundStateClient not importable from submission"

    try:
        bot = bot_class()
    except Exception as e:  # noqa: BLE001
        return module, None, RoundStateClient, f"Failed to instantiate {bot_class.__name__}: {e}"

    return module, bot, RoundStateClient, None


def query_move(move_func: Callable | None, state: dict, *, logger=None) -> Any:
    """Query a learner move function with a game *state* (offline evaluation).

    Directly calls the learner's ``move()`` / ``choose_move()`` / ``robot()``
    function and returns the action in its native format (dict for RoboCode,
    string for BattleSnake, …). BattleSnake-style ``{"move": "up"}`` responses
    are unwrapped to the bare direction; other games return the action directly.
    Returns ``None`` on error or when *move_func* is ``None``.

    Mirrors ``InverseStrategyTournament._query_learner``.
    """
    if move_func is None:
        return None
    try:
        result = move_func(state)
        # Unwrap BattleSnake-style {"move": "up"} responses; other games
        # (RoboCode, HuskyBench) return the action directly.
        if isinstance(result, dict) and "move" in result:
            return result["move"]
        return result
    except Exception as e:  # noqa: BLE001 - match tournament's tolerant replay
        if logger is not None:
            logger.debug(f"Error querying learner: {e}")
        return None


def make_inprocess_move_provider(
    move_func: Callable | None,
    *,
    logger=None,
) -> Callable[[dict], Any]:
    """Wrap an imported learner move function as a state -> action provider.

    Native tournament evaluation still uses this in-process provider. Harbor can
    supply a subprocess-backed provider while sharing the exact same trace
    scoring loop below.
    """

    def provider(state: dict) -> Any:
        return query_move(move_func, state, logger=logger)

    return provider


# --------------------------------------------------------------------------- #
# BattleSnake per-simulation scoring
# --------------------------------------------------------------------------- #
def score_battlesnake_simulations(
    sim_files: list[Path],
    round_dir: Path,
    target_name: str,
    move_func: Callable | None,
    *,
    logger=None,
) -> tuple[int, float, list[dict], list[dict]]:
    """Replay *move_func* against the frozen BattleSnake target traces.

    Returns ``(total_actions, total_distance, per_simulation, all_nonzero)``,
    exactly as accumulated by the per-simulation loop in
    ``InverseStrategyTournament._process_battlesnake_traces``.
    """
    return score_battlesnake_simulations_with_provider(
        sim_files,
        round_dir,
        target_name,
        make_inprocess_move_provider(move_func, logger=logger),
        logger=logger,
    )


def score_battlesnake_simulations_with_provider(
    sim_files: list[Path],
    round_dir: Path,
    target_name: str,
    move_provider: Callable[[dict], Any],
    *,
    logger=None,
) -> tuple[int, float, list[dict], list[dict]]:
    """Replay a learner action provider against BattleSnake target traces.

    ``move_provider`` receives the target-observed state and returns a
    BattleSnake action. The provider may be an in-process Python function
    (normal path) or a sandboxed subprocess bridge (Harbor); parsing, distance
    computation, and summary inputs stay shared.
    """
    from revenge_bench.traces.parsers.battlesnake import (
        actions_distance,
        extract_state_action_pairs,
    )

    total_actions = 0
    total_distance = 0.0
    per_simulation: list[dict] = []
    all_nonzero: list[dict] = []

    for sim_file in sim_files:
        try:
            sim_total = 0
            sim_expected = 0
            sim_skipped_none = 0
            sim_distance = 0.0
            sim_nonzero: list[dict] = []

            state_action_pairs = extract_state_action_pairs(sim_file, target_name)
            sim_expected = len(state_action_pairs)

            for turn_idx, (target_state, target_action) in enumerate(
                state_action_pairs
            ):
                learner_action = move_provider(target_state)
                if learner_action is None:
                    sim_skipped_none += 1
                    continue

                sim_total += 1
                distance = actions_distance(learner_action, target_action)
                sim_distance += distance

                if distance > 0.0:
                    entry = {
                        "sim_file": str(sim_file.relative_to(round_dir)),
                        "turn": target_state.get("turn", turn_idx),
                        "learner_action": learner_action,
                        "target_action": target_action,
                        "distance": distance,
                        "state": target_state,
                    }
                    sim_nonzero.append(entry)
                    all_nonzero.append(entry)

            total_actions += sim_total
            total_distance += sim_distance
            per_simulation.append(
                {
                    "file": str(sim_file.relative_to(round_dir)),
                    "total": sim_total,
                    "distance_sum": sim_distance,
                    "mean_distance": sim_distance / sim_total
                    if sim_total > 0
                    else 0.0,
                    "num_nonzero": len(sim_nonzero),
                    "expected_total": sim_expected,
                    "skipped_none": sim_skipped_none,
                }
            )
        except Exception as e:  # noqa: BLE001 - one bad sim must not abort the rest
            if logger is not None:
                logger.warning(f"Error processing {sim_file}: {e}")
            traceback.print_exc()
            continue

    return total_actions, total_distance, per_simulation, all_nonzero


def evaluate_battlesnake_submission_with_move_provider(
    round_dir: Path,
    round_num: int,
    target_name: str,
    learner_name: str,
    move_provider: Callable[[dict], Any],
    *,
    logger=None,
    evaluation_type: str = "offline",
    include_diagnostics: bool = False,
) -> dict[str, Any]:
    """Score BattleSnake traces using a caller-supplied learner action provider."""

    sim_files = find_battlesnake_sim_files(round_dir)
    if not sim_files:
        return {"error": f"No sim_*.jsonl files in {round_dir}"}

    total_actions, total_distance, per_simulation, all_nonzero = (
        score_battlesnake_simulations_with_provider(
            sim_files,
            round_dir,
            target_name,
            move_provider,
            logger=logger,
        )
    )

    return build_trace_summary(
        round_num,
        "BattleSnake",
        learner_name,
        target_name,
        evaluation_type,
        total_actions,
        total_distance,
        per_simulation,
        all_nonzero,
        include_diagnostics=include_diagnostics,
    )


# --------------------------------------------------------------------------- #
# Halite per-simulation scoring
# --------------------------------------------------------------------------- #
def score_halite_simulations_with_provider(
    sim_files: list[Path],
    round_dir: Path,
    target_hlt_name: str,
    action_provider: Callable[[dict, int], list],
    *,
    max_nonzero_distances: int | None = None,
    logger=None,
) -> tuple[int, float, list[dict], list[dict]]:
    """Replay a learner action provider against Halite I target traces.

    ``action_provider`` receives ``(hlt_data, player_tag)`` and returns the
    learner actions for every turn. Native evaluation supplies a compiled-bot
    provider; Harbor supplies the same kind of subprocess-backed provider while
    sharing this parser/distance/summary loop.
    """
    from revenge_bench.harbor.traces.parsers.halite import (
        actions_distance,
        extract_state_action_pairs,
        load_hlt_file,
    )

    total_actions = 0
    total_distance = 0.0
    per_simulation: list[dict] = []
    all_nonzero: list[dict] = []

    for sim_file in sim_files:
        try:
            sim_total = 0
            sim_expected = 0
            sim_distance = 0.0
            sim_nonzero: list[dict] = []

            state_action_pairs = extract_state_action_pairs(sim_file, target_hlt_name)
            sim_expected = len(state_action_pairs)

            hlt_data = load_hlt_file(sim_file)
            player_tag = hlt_data["player_names"].index(target_hlt_name) + 1
            learner_actions = action_provider(hlt_data, player_tag)

            for turn_idx, (target_state, target_action) in enumerate(
                state_action_pairs
            ):
                learner_action = (
                    learner_actions[turn_idx] if turn_idx < len(learner_actions) else []
                )

                sim_total += 1
                distance = actions_distance(learner_action, target_action)
                sim_distance += distance

                if distance > 0.0:
                    entry = {
                        "sim_file": str(sim_file.relative_to(round_dir)),
                        "turn": target_state.get("turn", turn_idx),
                        "learner_action": learner_action,
                        "target_action": target_action,
                        "distance": distance,
                        "state": target_state,
                    }
                    sim_nonzero.append(entry)
                    if (
                        max_nonzero_distances is None
                        or len(all_nonzero) < max_nonzero_distances
                    ):
                        all_nonzero.append(entry)

            total_actions += sim_total
            total_distance += sim_distance
            per_simulation.append(
                {
                    "file": str(sim_file.relative_to(round_dir)),
                    "total": sim_total,
                    "distance_sum": sim_distance,
                    "mean_distance": sim_distance / sim_total
                    if sim_total > 0
                    else 0.0,
                    "num_nonzero": len(sim_nonzero),
                    "expected_total": sim_expected,
                    "skipped_none": 0,
                }
            )
        except Exception as e:  # noqa: BLE001 - match native tolerant replay
            if logger is not None:
                logger.warning(f"Error processing {sim_file}: {e}")
            traceback.print_exc()
            continue

    return total_actions, total_distance, per_simulation, all_nonzero


def evaluate_halite_submission_with_action_provider(
    round_dir: Path,
    round_num: int,
    target_hlt_name: str,
    learner_name: str,
    action_provider: Callable[[dict, int], list],
    *,
    logger=None,
    evaluation_type: str = "offline_subprocess",
    include_diagnostics: bool = False,
    max_nonzero_distances: int | None = None,
) -> dict[str, Any]:
    """Score Halite I traces using a caller-supplied compiled-bot provider."""

    sim_files = find_halite_sim_files(round_dir)
    if not sim_files:
        return {"error": f"No .hlt files in {round_dir}"}

    total_actions, total_distance, per_simulation, all_nonzero = (
        score_halite_simulations_with_provider(
            sim_files,
            round_dir,
            target_hlt_name,
            action_provider,
            max_nonzero_distances=max_nonzero_distances,
            logger=logger,
        )
    )

    return build_trace_summary(
        round_num,
        "Halite",
        learner_name,
        target_hlt_name,
        evaluation_type,
        total_actions,
        total_distance,
        per_simulation,
        all_nonzero,
        include_diagnostics=include_diagnostics,
    )


# --------------------------------------------------------------------------- #
# RobotRumble per-simulation scoring
# --------------------------------------------------------------------------- #
def robotrumble_target_team_for_sim(
    sim_file: Path,
    *,
    fallback_target_team: str = "Blue",
) -> str:
    """Return the RobotRumble team assigned to the target for *sim_file*.

    Native multi-opponent runs write ``_target_team.txt`` next to each sim file
    after ``run_round`` shuffles player order. Single-opponent runs fall back to
    the tournament's ``self._rr_target_team`` value, defaulting to Blue.
    """
    team_file = sim_file.parent / "_target_team.txt"
    if team_file.exists():
        return team_file.read_text().strip()
    return fallback_target_team


def score_robotrumble_simulations_with_provider(
    sim_files: list[Path],
    round_dir: Path,
    action_provider: Callable[[list[dict]], list[Any]],
    *,
    fallback_target_team: str = "Blue",
    logger=None,
) -> tuple[int, float, list[dict], list[dict], str]:
    """Replay a learner action provider against RobotRumble target traces.

    ``action_provider`` receives the harness inputs that the native JS harness
    consumes and returns one learner action per input. The native path supplies a
    JS-subprocess provider, while Harbor can supply the same kind of trusted
    adapter. Parsing, team lookup, action distance, and aggregation stay shared.

    The returned ``summary_target_name`` intentionally mirrors the pre-existing
    native implementation: it is the parser target name from the last processed
    simulation. That field is cosmetic, but preserving it avoids hidden drift.
    """
    from revenge_bench.harbor.traces.parsers.robotrumble import (
        actions_distance,
        extract_state_action_pairs,
    )

    work_items: list[tuple[Path, int, dict, list[dict]]] = []
    summary_target_name = fallback_target_team
    for sim_file in sim_files:
        parser_target_name = robotrumble_target_team_for_sim(
            sim_file, fallback_target_team=fallback_target_team
        )
        summary_target_name = parser_target_name
        if logger is not None:
            logger.debug(
                f"RobotRumble target team for {sim_file.name}: {parser_target_name}"
            )
        try:
            for turn_idx, (target_state, target_action) in enumerate(
                extract_state_action_pairs(sim_file, parser_target_name)
            ):
                work_items.append((sim_file, turn_idx, target_state, target_action))
        except Exception as e:  # noqa: BLE001 - one bad sim must not abort the rest
            if logger is not None:
                logger.warning(f"Error parsing {sim_file}: {e}")

    if not work_items:
        return 0, 0.0, [], [], summary_target_name

    harness_inputs = [
        {
            "state": {"objs": state["all_objs"], "turn": state.get("turn", 0)},
            "team": state["team"],
        }
        for _, _, state, _ in work_items
    ]
    learner_actions = action_provider(harness_inputs)
    if len(learner_actions) != len(work_items):
        raise RuntimeError(
            f"RobotRumble action provider returned {len(learner_actions)} actions "
            f"for {len(work_items)} states"
        )

    total_actions = 0
    total_distance = 0.0
    per_simulation: list[dict] = []
    all_nonzero: list[dict] = []

    sim_groups: dict[str, list[tuple[int, dict, list[dict], Any]]] = {}
    for idx, (sim_file, turn_idx, target_state, target_action) in enumerate(
        work_items
    ):
        sim_key = str(sim_file.relative_to(round_dir))
        sim_groups.setdefault(sim_key, []).append(
            (turn_idx, target_state, target_action, learner_actions[idx])
        )

    for sim_key, items in sim_groups.items():
        sim_total = 0
        sim_expected = len(items)
        sim_distance = 0.0
        sim_nonzero: list[dict] = []

        for turn_idx, target_state, target_action, learner_action in items:
            sim_total += 1
            distance = actions_distance(learner_action, target_action)
            sim_distance += distance

            if distance > 0.0:
                entry = {
                    "sim_file": Path(sim_key).name,
                    "turn": target_state.get("turn", turn_idx),
                    "learner_action": learner_action,
                    "target_action": target_action,
                    "distance": distance,
                    "state": target_state,
                }
                sim_nonzero.append(entry)
                all_nonzero.append(entry)

        total_actions += sim_total
        total_distance += sim_distance
        per_simulation.append(
            {
                "file": sim_key,
                "total": sim_total,
                "distance_sum": sim_distance,
                "mean_distance": sim_distance / sim_total if sim_total > 0 else 0.0,
                "num_nonzero": len(sim_nonzero),
                "expected_total": sim_expected,
                "skipped_none": 0,
            }
        )

    return (
        total_actions,
        total_distance,
        per_simulation,
        all_nonzero,
        summary_target_name,
    )


def evaluate_robotrumble_submission_with_action_provider(
    round_dir: Path,
    round_num: int,
    learner_name: str,
    action_provider: Callable[[list[dict]], list[Any]],
    *,
    fallback_target_team: str = "Blue",
    logger=None,
    evaluation_type: str = "offline",
    include_diagnostics: bool = False,
) -> dict[str, Any]:
    """Score RobotRumble traces using a caller-supplied JS action provider."""

    sim_files = find_robotrumble_sim_files(round_dir)
    if not sim_files:
        return {"error": f"No sim_*.json files in {round_dir}"}

    (
        total_actions,
        total_distance,
        per_simulation,
        all_nonzero,
        summary_target_name,
    ) = score_robotrumble_simulations_with_provider(
        sim_files,
        round_dir,
        action_provider,
        fallback_target_team=fallback_target_team,
        logger=logger,
    )

    if total_actions == 0 and not per_simulation:
        return {"error": "No state-action pairs extracted from sim files"}

    return build_trace_summary(
        round_num,
        "RobotRumble",
        learner_name,
        summary_target_name,
        evaluation_type,
        total_actions,
        total_distance,
        per_simulation,
        all_nonzero,
        include_diagnostics=include_diagnostics,
    )


def make_robotrumble_js_action_provider(
    robot_js: Path,
    *,
    timeout: int = 120,
) -> Callable[[list[dict]], list[Any]]:
    """Wrap the native RobotRumble JS harness as a batch action provider."""
    from revenge_bench.utils.js_eval import run_js_eval

    parsers_dir = Path(__file__).resolve().parent / "parsers"
    harness_js = parsers_dir / "robotrumble_eval_harness.js"
    stdlib_js = parsers_dir / "robotrumble_stdlib.js"
    lodash_js = parsers_dir / "robotrumble_lodash.min.js"

    def provider(harness_inputs: list[dict]) -> list[Any]:
        input_lines = [
            json.dumps(item, separators=(",", ":")) for item in harness_inputs
        ]
        payload = "\n".join(input_lines) + "\n"
        result = run_js_eval(
            harness_js,
            stdlib_js,
            lodash_js,
            robot_js,
            payload=payload,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"JS evaluation failed: {(result.error or '')[:200]}"
            )
        output_lines = [
            line for line in result.stdout.strip().split("\n") if line.strip()
        ]
        if len(output_lines) != len(harness_inputs):
            raise RuntimeError(
                f"JS eval output mismatch: got {len(output_lines)} lines for "
                f"{len(harness_inputs)} states"
            )
        return [json.loads(line) for line in output_lines]

    return provider


def score_robocode_simulations_with_provider(
    sim_files: list[Path],
    round_dir: Path,
    parser_target_name: str | Callable[[Path], str],
    move_provider: Callable[[dict], Any],
    *,
    logger=None,
) -> tuple[int, float, list[dict], list[dict]]:
    """Replay a learner action provider against RoboCode target traces.

    This is the shared implementation of
    ``InverseStrategyTournament._process_robocode_traces``. It deliberately
    preserves that method's forgiving behavior: a failed trace is skipped, and
    a learner query returning ``None`` skips that turn.
    """
    from revenge_bench.harbor.traces.parsers.robocode import (
        actions_distance,
        extract_state_action_pairs,
    )

    total_actions = 0
    total_distance = 0.0
    per_simulation: list[dict] = []
    all_nonzero: list[dict] = []

    for sim_file in sim_files:
        try:
            parser_name = (
                parser_target_name(sim_file)
                if callable(parser_target_name)
                else parser_target_name
            )
            sim_total = 0
            sim_expected = 0
            sim_skipped_none = 0
            sim_distance = 0.0
            sim_nonzero: list[dict] = []

            state_action_pairs = extract_state_action_pairs(
                sim_file, parser_name
            )
            sim_expected = len(state_action_pairs)

            for turn_idx, (target_state, target_action) in enumerate(
                state_action_pairs
            ):
                learner_action = move_provider(target_state)
                if learner_action is None:
                    sim_skipped_none += 1
                    continue

                sim_total += 1
                distance = actions_distance(learner_action, target_action)
                sim_distance += distance

                if distance > 0.0:
                    entry = {
                        "sim_file": str(sim_file.relative_to(round_dir)),
                        "turn": target_state.get("turn", turn_idx),
                        "learner_action": learner_action,
                        "target_action": target_action,
                        "distance": distance,
                        "state": target_state,
                    }
                    sim_nonzero.append(entry)
                    all_nonzero.append(entry)

            total_actions += sim_total
            total_distance += sim_distance
            per_simulation.append(
                {
                    "file": str(sim_file.relative_to(round_dir)),
                    "total": sim_total,
                    "distance_sum": sim_distance,
                    "mean_distance": sim_distance / sim_total
                    if sim_total > 0
                    else 0.0,
                    "num_nonzero": len(sim_nonzero),
                    "expected_total": sim_expected,
                    "skipped_none": sim_skipped_none,
                }
            )
        except Exception as exc:  # noqa: BLE001 - mirrors tournament behavior
            if logger:
                logger.warning(f"Error processing {sim_file}: {exc}")
            traceback.print_exc()
            continue

    return total_actions, total_distance, per_simulation, all_nonzero


def evaluate_robocode_submission_with_move_provider(
    round_dir: Path,
    round_num: int,
    target_name: str,
    learner_name: str,
    move_provider: Callable[[dict], Any],
    *,
    parser_target_name: str | Callable[[Path], str] | None = None,
    evaluation_type: str = "offline",
    logger=None,
    include_diagnostics: bool = False,
) -> dict[str, Any]:
    """Score RoboCode traces using a caller-supplied learner move provider."""
    sim_files = find_robocode_sim_files(round_dir)
    if not sim_files:
        return {"error": f"No record_*.xml files in {round_dir}"}

    parser_target = parser_target_name or (
        lambda sim_file: robocode_parser_target_name_for_sim(sim_file, target_name)
    )

    total_actions, total_distance, per_simulation, all_nonzero = (
        score_robocode_simulations_with_provider(
            sim_files,
            round_dir,
            parser_target,
            move_provider,
            logger=logger,
        )
    )

    return build_trace_summary(
        round_num,
        "RoboCode",
        learner_name,
        target_name,
        evaluation_type,
        total_actions,
        total_distance,
        per_simulation,
        all_nonzero,
        include_diagnostics=include_diagnostics,
    )


# --------------------------------------------------------------------------- #
# HuskyBench scoring
# --------------------------------------------------------------------------- #
def query_huskybench_bot(
    bot: Any,
    RoundStateClient: Any,
    state: dict,
) -> str | None:
    """Query a loaded HuskyBench Bot with a reconstructed parser state."""
    import contextlib
    import io

    from revenge_bench.harbor.traces.parsers.huskybench import normalize_action

    player_bets = {"0": 0, "1": 0}
    player_actions = {}
    for ah in state.get("action_history", []):
        pid = "0" if ah["player"] == "you" else "1"
        player_bets[pid] = player_bets.get(pid, 0) + ah.get("amount", 0)
        player_actions[pid] = ah.get("action", "")

    remaining_chips = state.get("my_stack", 10000)
    blinds = state.get("blinds", {})

    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            bot.on_start(
                remaining_chips,
                state.get("hole_cards", []),
                blinds.get("big", 10),
                1,
                0,
                [0, 1],
            )
    except Exception:
        pass

    try:
        round_state = RoundStateClient(
            round_num=state.get("hand_number", 0),
            round=state.get("round", "preflop"),
            community_cards=state.get("community_cards", []),
            pot=state.get("pot", 0),
            current_player=[0],
            current_bet=state.get("current_bet", 0),
            min_raise=blinds.get("big", 10),
            max_raise=remaining_chips,
            player_bets=player_bets,
            player_actions=player_actions,
            player_money={
                "0": remaining_chips,
                "1": state["opponent_stacks"][0]
                if state.get("opponent_stacks")
                else 10000,
            },
            side_pots=[],
        )
    except Exception:
        return None

    try:
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                bot.on_round_start(round_state, remaining_chips)
        except Exception:
            pass
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            result = bot.get_action(round_state, remaining_chips)
        if isinstance(result, tuple) and len(result) == 2:
            poker_action, amount = result
            action_name = poker_action.name
            if action_name == "ALL_IN":
                return "RAISE:1.0000"
            if action_name == "RAISE":
                return normalize_action(
                    {"action": "RAISE", "amount": amount},
                    player_stack=remaining_chips,
                )
            return action_name
    except Exception:
        pass
    return None


def make_huskybench_bot_action_provider(
    submission_py: Path,
    code_dir: Path,
) -> tuple[Callable[[dict], Any] | None, str | None]:
    """Load a HuskyBench Bot and return a ``state -> action`` provider."""
    _module, bot, RoundStateClient, error = load_huskybench_bot(submission_py, code_dir)
    if error is not None or bot is None or RoundStateClient is None:
        return None, error

    def provider(state: dict) -> Any:
        return query_huskybench_bot(bot, RoundStateClient, state)

    return provider, None


def score_huskybench_simulations_with_provider(
    sim_files: list[Path],
    round_dir: Path,
    target_name: str,
    action_provider: Callable[[dict], Any],
    *,
    logger=None,
) -> tuple[int, float, list[dict], list[dict]]:
    """Replay a HuskyBench action provider against frozen poker traces."""
    from revenge_bench.harbor.traces.parsers.huskybench import (
        actions_distance,
        extract_state_action_pairs,
    )

    total_actions = 0
    total_distance = 0.0
    per_simulation: list[dict] = []
    all_nonzero: list[dict] = []

    for sim_file in sim_files:
        try:
            sim_total = 0
            sim_expected = 0
            sim_skipped_none = 0
            sim_distance = 0.0
            sim_nonzero: list[dict] = []

            state_action_pairs = extract_state_action_pairs(sim_file, target_name)
            sim_expected = len(state_action_pairs)
            for turn_idx, (target_state, target_action) in enumerate(
                state_action_pairs
            ):
                learner_action = action_provider(target_state)
                if learner_action is None:
                    sim_skipped_none += 1
                    continue

                sim_total += 1
                distance = actions_distance(
                    learner_action,
                    target_action,
                    player_stack=target_state.get("my_stack"),
                )
                sim_distance += distance

                if distance > 0.0:
                    entry = {
                        "sim_file": str(sim_file.relative_to(round_dir)),
                        "turn": target_state.get("turn", turn_idx),
                        "learner_action": learner_action,
                        "target_action": target_action,
                        "distance": distance,
                        "state": target_state,
                    }
                    sim_nonzero.append(entry)
                    all_nonzero.append(entry)

            total_actions += sim_total
            total_distance += sim_distance
            per_simulation.append(
                {
                    "file": str(sim_file.relative_to(round_dir)),
                    "total": sim_total,
                    "distance_sum": sim_distance,
                    "mean_distance": sim_distance / sim_total
                    if sim_total > 0
                    else 0.0,
                    "num_nonzero": len(sim_nonzero),
                    "expected_total": sim_expected,
                    "skipped_none": sim_skipped_none,
                }
            )
        except Exception as e:  # noqa: BLE001 - one bad sim must not abort
            if logger is not None:
                logger.warning(f"Error processing {sim_file}: {e}")
            traceback.print_exc()
            continue

    return total_actions, total_distance, per_simulation, all_nonzero


def evaluate_huskybench_submission_with_action_provider(
    round_dir: Path,
    round_num: int,
    target_name: str,
    learner_name: str,
    action_provider: Callable[[dict], Any],
    *,
    evaluation_type: str = "offline_bot_class",
    logger=None,
    include_diagnostics: bool = False,
) -> dict[str, Any]:
    """Score HuskyBench traces using a caller-supplied action provider."""
    sim_files = find_huskybench_sim_files(round_dir)
    if not sim_files:
        return {"error": f"No game_log_*.json files in {round_dir}"}

    total_actions, total_distance, per_simulation, all_nonzero = (
        score_huskybench_simulations_with_provider(
            sim_files,
            round_dir,
            target_name,
            action_provider,
            logger=logger,
        )
    )

    return build_trace_summary(
        round_num,
        "HuskyBench",
        learner_name,
        target_name,
        evaluation_type,
        total_actions,
        total_distance,
        per_simulation,
        all_nonzero,
        include_diagnostics=include_diagnostics,
    )


# --------------------------------------------------------------------------- #
# Trace summary + component-error breakdown
# --------------------------------------------------------------------------- #
def compute_component_errors(
    all_nonzero: list[dict], total_actions: int
) -> dict[str, Any] | None:
    """Compute per-component error statistics from nonzero distance entries.

    Returns a dict mapping component name to error stats, plus which components
    contribute the most overall error. Returns ``None`` if the RoboCode parser
    (which defines the action components) is unavailable.

    Mirrors ``InverseStrategyTournament._compute_component_errors``.
    """
    try:
        from revenge_bench.harbor.traces.parsers.robocode import (
            ACTION_COMPONENTS,
            ACTION_RANGES,
        )
    except ImportError:
        return None

    # Accumulate per-component absolute errors
    comp_sums: dict[str, float] = {c: 0.0 for c in ACTION_COMPONENTS}
    comp_counts: dict[str, int] = {c: 0 for c in ACTION_COMPONENTS}
    comp_max: dict[str, float] = {c: 0.0 for c in ACTION_COMPONENTS}

    for entry in all_nonzero:
        la = entry.get("learner_action", {})
        ta = entry.get("target_action", {})
        for comp in ACTION_COMPONENTS:
            lv = la.get(comp, 0.0)
            tv = ta.get(comp, 0.0)
            rng = ACTION_RANGES[comp]
            max_diff = rng if comp == "fire_power" else 2.0 * rng
            normed = min(abs(lv - tv) / max_diff, 1.0)
            comp_sums[comp] += normed
            if normed > 0:
                comp_counts[comp] += 1
            if normed > comp_max[comp]:
                comp_max[comp] = normed

    result = {}
    for comp in ACTION_COMPONENTS:
        rng = ACTION_RANGES[comp]
        max_diff = rng if comp == "fire_power" else 2.0 * rng
        mean_err = comp_sums[comp] / total_actions if total_actions > 0 else 0.0
        result[comp] = {
            "mean_normalized_error": round(mean_err, 6),
            "nonzero_count": comp_counts[comp],
            "max_normalized_error": round(comp_max[comp], 6),
            "range": f"[{-rng if comp != 'fire_power' else 0}, {rng}]",
            "max_abs_diff": max_diff,
        }

    # Rank by contribution to overall error
    ranked = sorted(
        ACTION_COMPONENTS,
        key=lambda c: result[c]["mean_normalized_error"],
        reverse=True,
    )
    result["worst_to_best"] = ranked

    return result


def build_trace_summary(
    round_num: int,
    game_name: str,
    learner_name: str,
    target_name: str,
    evaluation_type: str,
    total_actions: int,
    total_distance: float,
    per_simulation: list[dict],
    all_nonzero: list[dict],
    *,
    include_diagnostics: bool = False,
) -> dict[str, Any]:
    """Compute the offline-evaluation summary dict (does **not** write a file).

    Mirrors the computation in
    ``InverseStrategyTournament._build_trace_summary`` exactly; the tournament
    wrapper is responsible for persisting the result to ``traces.json`` and
    logging, so both the tournament and the Harbor verifier share identical
    statistics while choosing where to store them.
    """
    mean_distance = (
        total_distance / total_actions if total_actions > 0 else float("inf")
    )

    sim_mean_distances = [s["mean_distance"] for s in per_simulation if s["total"] > 0]
    if sim_mean_distances:
        mean_distance_across_sims = statistics.mean(sim_mean_distances)
        distance_std = (
            statistics.stdev(sim_mean_distances)
            if len(sim_mean_distances) > 1
            else 0.0
        )
        distance_se = distance_std / (len(sim_mean_distances) ** 0.5)
    else:
        mean_distance_across_sims = float("inf")
        distance_std = 0.0
        distance_se = 0.0

    if include_diagnostics:
        output_per_simulation = per_simulation
        expected_actions = sum(
            int(s.get("expected_total", s.get("total", 0))) for s in per_simulation
        )
        skipped_none_actions = sum(int(s.get("skipped_none", 0)) for s in per_simulation)
        skipped_none_fraction = (
            skipped_none_actions / expected_actions if expected_actions > 0 else 0.0
        )
    else:
        # Preserve the pre-Harbor normal-path traces.json schema byte-for-byte:
        # diagnostic keys are useful for Harbor audit logs, but the native
        # benchmark historically did not emit them.
        output_per_simulation = [
            {
                key: value
                for key, value in sim.items()
                if key not in {"expected_total", "skipped_none"}
            }
            for sim in per_simulation
        ]

    summary: dict[str, Any] = {
        "round": round_num,
        "game": game_name,
        "learner": learner_name,
        "target": target_name,
        "evaluation_type": evaluation_type,
        "total_actions": total_actions,
        "total_distance": total_distance,
        "mean_distance": mean_distance,
        "mean_distance_across_sims": mean_distance_across_sims,
        "distance_std": distance_std,
        "distance_se": distance_se,
        "num_simulations": len(per_simulation),
        "per_simulation": output_per_simulation,
    }
    if include_diagnostics:
        summary["scored_actions"] = total_actions
        summary["expected_actions"] = expected_actions
        summary["skipped_none_actions"] = skipped_none_actions
        summary["skipped_none_fraction"] = skipped_none_fraction

    # Per-component error breakdown (RoboCode: 5-component actions)
    if (
        all_nonzero
        and isinstance(all_nonzero[0].get("learner_action"), dict)
        and isinstance(all_nonzero[0].get("target_action"), dict)
    ):
        component_errors = compute_component_errors(all_nonzero, total_actions)
        if component_errors:
            summary["component_errors"] = component_errors

    summary["nonzero_distances"] = all_nonzero

    return summary


# --------------------------------------------------------------------------- #
# High-level entry point for the Harbor in-container verifier
# --------------------------------------------------------------------------- #
def evaluate_battlesnake_submission(
    round_dir: Path,
    round_num: int,
    target_name: str,
    learner_name: str,
    learner_code_dir: Path,
    submission: str = "main.py",
    *,
    logger=None,
    include_diagnostics: bool = False,
) -> dict[str, Any]:
    """Score a BattleSnake submission against the frozen traces in *round_dir*.

    This is the convenience entry point used by the Harbor verifier: it globs
    the frozen ``sim_*.jsonl`` traces, loads the learner's move function from
    *learner_code_dir*, replays it, and returns the same summary dict the
    tournament writes to ``traces.json``. On a missing submission or an
    unscorable policy it returns ``{"error": ...}`` (matching the tournament's
    failure signalling).
    """
    sim_files = find_battlesnake_sim_files(round_dir)
    if not sim_files:
        return {"error": f"No sim_*.jsonl files in {round_dir}"}

    submission_py, code_dir = resolve_submission_path(learner_code_dir, submission)
    if not submission_py.exists():
        return {"error": f"Learner {submission} not found at {submission_py}"}

    module, move_func, _kind = load_move_function(submission_py, code_dir)
    if module is None or move_func is None:
        return {
            "error": "Failed to load learner module (check that main.py defines a valid move() function)"
        }

    return evaluate_battlesnake_submission_with_move_provider(
        round_dir=round_dir,
        round_num=round_num,
        target_name=target_name,
        learner_name=learner_name,
        move_provider=make_inprocess_move_provider(move_func, logger=logger),
        logger=logger,
        evaluation_type="offline",
        include_diagnostics=include_diagnostics,
    )
