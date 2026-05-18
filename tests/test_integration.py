"""
Integration test for main.py with BattleSnake configuration.

This test verifies that the main execution flow works without exceptions,
using DeterministicModel instead of real LLM models.
"""

import shutil
import subprocess

import pytest

from revenge_bench import CONFIG_DIR


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=5).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="Docker daemon not available")


def test_pvp_battlesnake():
    from main import main_cli

    config_path = CONFIG_DIR / "test" / "battlesnake_pvp_test.yaml"
    main_cli(["-c", str(config_path)])
