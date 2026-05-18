"""Regression test: the per-shell-command timeout for agent environments
must stay tight enough to catch runaway commands but loose enough not to
fire on legitimate work. See plan 2026-05-01-...-timeout-fixes.md."""
from pathlib import Path
import re


ARENA_PY = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "revenge_bench" / "arenas" / "arena.py"
)
EXPECTED_TIMEOUT_SECONDS = 600


def test_singularity_environment_uses_expected_timeout():
    src = ARENA_PY.read_text()
    # Find the SingularityEnvironment(...) block and pull out timeout=N.
    m = re.search(
        r"SingularityEnvironment\(.*?timeout=(\d+).*?\)",
        src, re.DOTALL,
    )
    assert m, "Could not locate SingularityEnvironment(...) in arena.py"
    assert int(m.group(1)) == EXPECTED_TIMEOUT_SECONDS, (
        f"SingularityEnvironment timeout must be {EXPECTED_TIMEOUT_SECONDS}s "
        f"(found {m.group(1)}s). Lower than this risks timing out legit "
        f"compiles; higher risks runaway LLM commands jamming SLURM tasks."
    )


def test_docker_environment_uses_expected_timeout():
    src = ARENA_PY.read_text()
    # Match a timeout= within the DockerEnvironment(...) block, distinct
    # from container_timeout=.
    m = re.search(
        r"DockerEnvironment\((?:[^()]|\([^()]*\))*?(?<!container_)timeout=(\d+)",
        src, re.DOTALL,
    )
    assert m, "Could not locate DockerEnvironment(timeout=...) in arena.py"
    assert int(m.group(1)) == EXPECTED_TIMEOUT_SECONDS, (
        f"DockerEnvironment timeout must be {EXPECTED_TIMEOUT_SECONDS}s "
        f"(found {m.group(1)}s)."
    )
