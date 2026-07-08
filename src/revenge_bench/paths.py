"""Paths owned by RevengeBench.

Source checkouts keep benchmark assets at the repository root. Built wheels
install those same assets under ``revenge_bench/assets``; the helpers below
prefer the source-tree paths when present and otherwise fall back to the
installed package data location.
"""

from pathlib import Path


def _asset_dir(name: str) -> Path:
    repo_path = REPO_ROOT / name
    if repo_path.exists():
        return repo_path
    return PACKAGE_DIR / "assets" / name

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = REPO_DIR
CONFIG_DIR = _asset_dir("configs")
DATA_DIR = _asset_dir("data")
LOG_DIR = REPO_ROOT / "logs"
LOCAL_LOG_DIR = LOG_DIR
