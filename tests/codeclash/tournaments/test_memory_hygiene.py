"""Smoke tests pinning the memory-hygiene fix from reverted PR #46."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _function_source(file_path: Path, qualname: str) -> str:
    """Return the source of a method `Class.method` or top-level function."""
    tree = ast.parse(file_path.read_text())
    parts = qualname.split(".")
    node = tree
    for part in parts:
        candidates = [
            n for n in ast.walk(node)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and n.name == part
        ]
        assert candidates, f"could not find {part!r} under {qualname!r}"
        node = candidates[0]
    return ast.unparse(node)


def test_inverse_strategy_imports_gc():
    src = (REPO_ROOT / "src/revenge_bench/tournaments/inverse_strategy.py").read_text()
    assert "import gc" in src, "inverse_strategy.py must import gc for memory hygiene"


def test_inverse_strategy_frees_trace_summary():
    """Round-finalization must drop and gc the large trace_summary dict."""
    src = _function_source(
        REPO_ROOT / "src/revenge_bench/tournaments/inverse_strategy.py",
        "InverseStrategyTournament",
    )
    # Look anywhere in the class for the pattern.
    assert "del trace_summary" in src
    assert "gc.collect()" in src


def test_inverse_strategy_frees_traces_json():
    src = _function_source(
        REPO_ROOT / "src/revenge_bench/tournaments/inverse_strategy.py",
        "InverseStrategyTournament",
    )
    assert "del traces_json" in src


def test_observation_summarizer_frees_pool():
    src = (REPO_ROOT / "src/revenge_bench/tournaments/observation_summarizer.py").read_text()
    # del pool must appear inside _format_traces_for_summarizer
    func = _function_source(
        REPO_ROOT / "src/revenge_bench/tournaments/observation_summarizer.py",
        "_format_traces_for_summarizer",
    )
    assert "del pool" in func, "observation_summarizer must free the pool copy"
