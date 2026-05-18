# Trace logging for game dynamics
from revenge_bench.traces.collector import TraceCollector, collect_traces
from revenge_bench.traces.models import (
    STATE_SCHEMAS,
    GameMetadata,
    GameOutcome,
    GameTrace,
    PlayerAction,
    PlayerResult,
    TurnRecord,
)
from revenge_bench.traces.parsers import get_parser
from revenge_bench.traces.reader import (
    TraceReader,
    get_state_action_dataset,
    iter_traces,
    read_trace,
)
from revenge_bench.traces.writer import TraceWriter, write_trace

__all__ = [
    # Core models
    "GameTrace",
    "TurnRecord",
    "GameMetadata",
    "PlayerAction",
    "PlayerResult",
    "GameOutcome",
    "STATE_SCHEMAS",
    # Writer
    "TraceWriter",
    "write_trace",
    # Reader
    "TraceReader",
    "read_trace",
    "iter_traces",
    "get_state_action_dataset",
    # Collector
    "TraceCollector",
    "collect_traces",
    # Parsers
    "get_parser",
]
