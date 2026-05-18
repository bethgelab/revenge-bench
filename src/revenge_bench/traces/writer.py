"""
Trace Writer - Handles writing game traces to disk.

Supports two formats:
1. JSONL (JSON Lines): One JSON object per line, good for streaming
2. JSON: Single JSON file with the complete trace

For large traces or streaming scenarios, prefer JSONL.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import IO, Any

from revenge_bench.traces.models import GameMetadata, GameTrace, PlayerResult, TurnRecord


class TraceWriter:
    """
    Writes game traces to disk in JSONL or JSON format.

    Usage for streaming (JSONL):
        writer = TraceWriter(path, format="jsonl")
        writer.write_metadata(metadata)
        for turn in turns:
            writer.write_turn(turn)
        writer.write_results(results, winner, is_draw)
        writer.close()

    Usage for complete trace (JSON):
        writer = TraceWriter(path, format="json")
        writer.write_trace(trace)
        writer.close()

    Or use as context manager:
        with TraceWriter(path) as writer:
            writer.write_trace(trace)
    """

    def __init__(
        self,
        path: str | Path,
        format: str = "jsonl",
        compress: bool = False,
    ):
        """
        Initialize the trace writer.

        Args:
            path: Output file path
            format: "jsonl" for streaming, "json" for complete trace
            compress: Whether to gzip compress the output
        """
        self.path = Path(path)
        self.format = format
        self.compress = compress
        self._file: IO | None = None
        self._turns_written = 0
        self._metadata_written = False

        # Ensure parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Add appropriate extension
        if compress and not self.path.suffix.endswith(".gz"):
            self.path = self.path.with_suffix(self.path.suffix + ".gz")

    def _open(self) -> IO:
        """Open the output file."""
        if self._file is None:
            if self.compress:
                self._file = gzip.open(self.path, "wt", encoding="utf-8")
            else:
                self._file = open(self.path, "w", encoding="utf-8")
        return self._file

    def close(self) -> None:
        """Close the output file."""
        if self._file is not None:
            self._file.close()
            self._file = None

    def __enter__(self) -> TraceWriter:
        self._open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _write_line(self, obj: dict[str, Any]) -> None:
        """Write a single JSON line."""
        f = self._open()
        json.dump(obj, f, separators=(",", ":"))
        f.write("\n")

    # -------------------------------------------------------------------------
    # JSONL Streaming Methods
    # -------------------------------------------------------------------------

    def write_metadata(self, metadata: GameMetadata) -> None:
        """Write the metadata as the first line (JSONL mode)."""
        if self.format != "jsonl":
            raise ValueError("write_metadata only works in JSONL format")

        self._write_line(
            {
                "type": "metadata",
                "data": metadata.to_dict(),
            }
        )
        self._metadata_written = True

    def write_turn(self, turn: TurnRecord) -> None:
        """Write a single turn record (JSONL mode)."""
        if self.format != "jsonl":
            raise ValueError("write_turn only works in JSONL format")

        self._write_line(
            {
                "type": "turn",
                "data": turn.to_dict(),
            }
        )
        self._turns_written += 1

    def write_results(
        self,
        results: list[PlayerResult],
        winner: str | None = None,
        is_draw: bool = False,
    ) -> None:
        """Write the final results as the last line (JSONL mode)."""
        if self.format != "jsonl":
            raise ValueError("write_results only works in JSONL format")

        self._write_line(
            {
                "type": "results",
                "data": {
                    "results": [r.to_dict() for r in results],
                    "winner": winner,
                    "is_draw": is_draw,
                    "total_turns": self._turns_written,
                },
            }
        )

    # -------------------------------------------------------------------------
    # JSON Complete Trace Method
    # -------------------------------------------------------------------------

    def write_trace(self, trace: GameTrace) -> None:
        """Write a complete trace (JSON mode)."""
        f = self._open()

        if self.format == "json":
            json.dump(trace.to_dict(), f, indent=2)
        else:
            # JSONL format - write metadata, turns, then results
            self.write_metadata(trace.metadata)
            for turn in trace.turns:
                self.write_turn(turn)
            self.write_results(trace.results, trace.winner, trace.is_draw)


def write_trace(trace: GameTrace, path: str | Path, **kwargs) -> Path:
    """
    Convenience function to write a trace to disk.

    Args:
        trace: The GameTrace to write
        path: Output path
        **kwargs: Additional arguments for TraceWriter

    Returns:
        The path where the trace was written
    """
    with TraceWriter(path, **kwargs) as writer:
        writer.write_trace(trace)
    return writer.path
