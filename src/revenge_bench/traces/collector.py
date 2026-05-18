"""
Trace Collector - Collects and parses traces from game simulations.

This module integrates with the arena system to collect game traces
after simulations complete. Each game type has its own parser that
converts the native output format to our unified GameTrace format.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from revenge_bench.traces.models import GameTrace
from revenge_bench.traces.parsers import TRACE_PARSERS
from revenge_bench.traces.writer import TraceWriter


class TraceCollector:
    """
    Collects traces from game simulations and converts them to our format.

    Usage:
        collector = TraceCollector(game_type="BattleSnake")

        # Collect traces from a round's log directory
        traces = collector.collect_from_round(
            log_dir=arena.log_round(round_num),
            source={"tournament_id": "...", "round": round_num}
        )

        # Save collected traces
        collector.save_traces(traces, output_dir)
    """

    def __init__(self, game_type: str):
        """
        Initialize the collector.

        Args:
            game_type: Type of game (BattleSnake, CoreWar, etc.)
        """
        self.game_type = game_type

        if game_type not in TRACE_PARSERS:
            raise ValueError(f"No trace parser for game type: {game_type}")

        self.parser_class = TRACE_PARSERS[game_type]
        self.parser = self.parser_class()

    def collect_from_round(
        self,
        log_dir: Path | str,
        source: dict | None = None,
    ) -> list[GameTrace]:
        """
        Collect traces from a round's log directory.

        Args:
            log_dir: Path to the round's log directory
            source: Optional source metadata to attach to traces

        Returns:
            List of GameTrace objects
        """
        log_dir = Path(log_dir)
        traces = []

        # Find all simulation output files
        pattern = self._get_file_pattern()
        for trace_file in sorted(log_dir.glob(pattern)):
            try:
                trace = self.parser.parse_file(trace_file, source=source)
                trace.metadata.source["file"] = trace_file.name
                traces.append(trace)
            except Exception as e:
                print(f"Warning: Failed to parse {trace_file}: {e}")

        return traces

    def collect_from_tournament(
        self,
        tournament_dir: Path | str,
        tournament_id: str | None = None,
    ) -> Iterator[GameTrace]:
        """
        Collect all traces from a tournament's log directory.

        Args:
            tournament_dir: Path to the tournament's output directory
            tournament_id: Optional tournament ID for source metadata

        Yields:
            GameTrace objects
        """
        tournament_dir = Path(tournament_dir)
        rounds_dir = tournament_dir / "rounds"

        if not rounds_dir.exists():
            return

        for round_dir in sorted(rounds_dir.iterdir()):
            if not round_dir.is_dir():
                continue

            try:
                round_num = int(round_dir.name)
            except ValueError:
                continue

            source = {
                "tournament_id": tournament_id or tournament_dir.name,
                "round": round_num,
            }

            yield from self.collect_from_round(round_dir, source=source)

    def save_traces(
        self,
        traces: list[GameTrace],
        output_dir: Path | str,
        format: str = "jsonl",
        compress: bool = False,
    ) -> list[Path]:
        """
        Save collected traces to disk.

        Args:
            traces: List of traces to save
            output_dir: Output directory
            format: Output format ("jsonl" or "json")
            compress: Whether to gzip compress

        Returns:
            List of paths where traces were saved
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        saved_paths = []
        for i, trace in enumerate(traces):
            filename = f"trace_{trace.game_id}_{i:04d}"
            if format == "jsonl":
                filename += ".jsonl"
            else:
                filename += ".json"

            path = output_dir / filename
            with TraceWriter(path, format=format, compress=compress) as writer:
                writer.write_trace(trace)
            saved_paths.append(writer.path)

        return saved_paths

    def _get_file_pattern(self) -> str:
        """Get the glob pattern for finding trace files."""
        # BattleSnake outputs sim_0.jsonl, sim_1.jsonl, etc.
        patterns = {
            "BattleSnake": "sim_*.jsonl",
            "CoreWar": "*.log",  # TODO: Implement CoreWar parser
            "Halite": "replay-*.hlt",
            "Halite2": "replay-*.hlt",
            "Halite3": "replay-*.hlt",
            "RoboCode": "*.xml",  # TODO: Implement RoboCode parser
            "RobotRumble": "*.json",
            "HuskyBench": "game_log_*.json",
        }
        return patterns.get(self.game_type, "*.jsonl")


def collect_traces(
    game_type: str,
    log_dir: Path | str,
    output_dir: Path | str | None = None,
    **kwargs,
) -> list[GameTrace]:
    """
    Convenience function to collect and optionally save traces.

    Args:
        game_type: Type of game
        log_dir: Directory containing simulation outputs
        output_dir: Optional directory to save converted traces
        **kwargs: Additional arguments for TraceCollector.save_traces

    Returns:
        List of collected traces
    """
    collector = TraceCollector(game_type)
    traces = collector.collect_from_round(log_dir)

    if output_dir:
        collector.save_traces(traces, output_dir, **kwargs)

    return traces
