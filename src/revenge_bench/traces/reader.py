"""
Trace Reader - Handles reading game traces from disk.

Supports:
1. JSONL format (streaming)
2. JSON format (complete trace)
3. Gzip compressed files
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from revenge_bench.traces.models import (
    GameMetadata,
    GameTrace,
    PlayerResult,
    TurnRecord,
)


class TraceReader:
    """
    Reads game traces from disk.

    Supports both JSONL and JSON formats, auto-detected from content.

    Usage:
        # Read complete trace
        trace = TraceReader.read(path)

        # Stream turns (for large files)
        reader = TraceReader(path)
        metadata = reader.read_metadata()
        for turn in reader.iter_turns():
            process(turn)
    """

    def __init__(self, path: str | Path):
        """
        Initialize the trace reader.

        Args:
            path: Path to the trace file (JSON, JSONL, or .gz compressed)
        """
        self.path = Path(path)
        self._is_compressed = self.path.suffix == ".gz"
        self._format: str | None = None

    def _open(self):
        """Open the file with appropriate decompression."""
        if self._is_compressed:
            return gzip.open(self.path, "rt", encoding="utf-8")
        return open(self.path, encoding="utf-8")

    def _detect_format(self) -> str:
        """Detect whether the file is JSON or JSONL."""
        if self._format is not None:
            return self._format

        with self._open() as f:
            first_line = f.readline().strip()
            if not first_line:
                raise ValueError(f"Empty trace file: {self.path}")

            # Try to parse as JSON
            try:
                data = json.loads(first_line)
                # If it has "metadata" and "turns" at top level, it's a complete JSON
                if "metadata" in data and "turns" in data:
                    self._format = "json"
                # If it has "type" field, it's JSONL
                elif "type" in data:
                    self._format = "jsonl"
                else:
                    # Assume JSONL if line-by-line JSON
                    self._format = "jsonl"
            except json.JSONDecodeError:
                # Not valid JSON on first line - might be pretty-printed JSON
                self._format = "json"

        return self._format

    def read_metadata(self) -> GameMetadata:
        """Read just the metadata from the trace."""
        format = self._detect_format()

        with self._open() as f:
            if format == "json":
                data = json.load(f)
                return GameMetadata.from_dict(data["metadata"])
            else:  # jsonl
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if record.get("type") == "metadata":
                        return GameMetadata.from_dict(record["data"])

        raise ValueError(f"No metadata found in trace: {self.path}")

    def iter_turns(self) -> Iterator[TurnRecord]:
        """
        Iterate over turns in the trace.

        This is memory-efficient for large traces.
        """
        format = self._detect_format()

        with self._open() as f:
            if format == "json":
                data = json.load(f)
                for turn_data in data.get("turns", []):
                    yield TurnRecord.from_dict(turn_data)
            else:  # jsonl
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if record.get("type") == "turn":
                        yield TurnRecord.from_dict(record["data"])

    def read(self) -> GameTrace:
        """
        Read the complete trace into memory.

        Returns:
            Complete GameTrace object
        """
        format = self._detect_format()

        with self._open() as f:
            if format == "json":
                data = json.load(f)
                return GameTrace.from_dict(data)
            else:  # jsonl
                metadata = None
                turns = []
                results = []
                winner = None
                is_draw = False

                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    record_type = record.get("type")

                    if record_type == "metadata":
                        metadata = GameMetadata.from_dict(record["data"])
                    elif record_type == "turn":
                        turns.append(TurnRecord.from_dict(record["data"]))
                    elif record_type == "results":
                        results_data = record["data"]
                        results = [
                            PlayerResult.from_dict(r)
                            for r in results_data.get("results", [])
                        ]
                        winner = results_data.get("winner")
                        is_draw = results_data.get("is_draw", False)

                if metadata is None:
                    raise ValueError(f"No metadata found in trace: {self.path}")

                return GameTrace(
                    metadata=metadata,
                    turns=turns,
                    results=results,
                    winner=winner,
                    is_draw=is_draw,
                )

    @classmethod
    def read_file(cls, path: str | Path) -> GameTrace:
        """
        Convenience class method to read a trace file.

        Args:
            path: Path to the trace file

        Returns:
            Complete GameTrace object
        """
        return cls(path).read()


def read_trace(path: str | Path) -> GameTrace:
    """
    Convenience function to read a trace from disk.

    Args:
        path: Path to the trace file

    Returns:
        Complete GameTrace object
    """
    return TraceReader.read_file(path)


def iter_traces(directory: str | Path, pattern: str = "*.jsonl") -> Iterator[GameTrace]:
    """
    Iterate over all trace files in a directory.

    Args:
        directory: Directory containing trace files
        pattern: Glob pattern for trace files

    Yields:
        GameTrace objects
    """
    directory = Path(directory)
    for path in sorted(directory.glob(pattern)):
        try:
            yield read_trace(path)
        except Exception as e:
            print(f"Warning: Failed to read {path}: {e}")


def get_state_action_dataset(
    traces: list[GameTrace] | Iterator[GameTrace],
    player_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Extract a flat dataset of (state, action) pairs from traces.

    This is the key function for preparing training/evaluation data
    for strategy inference.

    Args:
        traces: List or iterator of GameTrace objects
        player_filter: Optional player name to filter by

    Returns:
        List of dicts with keys: game_id, game_type, turn, player_name, state, action
    """
    dataset = []

    for trace in traces:
        for turn in trace.turns:
            for action in turn.actions:
                if player_filter and action.player_name != player_filter:
                    continue

                # Get player-specific state if available
                state = turn.player_states.get(action.player_name, turn.state)

                dataset.append(
                    {
                        "game_id": trace.game_id,
                        "game_type": trace.game_type,
                        "turn": turn.turn,
                        "player_id": action.player_id,
                        "player_name": action.player_name,
                        "state": state,
                        "action": action.action,
                        "valid_actions": action.valid_actions,
                    }
                )

    return dataset
