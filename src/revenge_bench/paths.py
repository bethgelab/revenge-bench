"""Repository-local paths owned by RevengeBench."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = REPO_DIR
CONFIG_DIR = REPO_ROOT / "configs"
DATA_DIR = REPO_ROOT / "data"
LOG_DIR = REPO_ROOT / "logs"
LOCAL_LOG_DIR = LOG_DIR
