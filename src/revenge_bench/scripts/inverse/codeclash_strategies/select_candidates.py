#!/usr/bin/env python3
"""Round-2 selection: dedup, score complexity, and sample candidates for Elo.

Takes the Round-1 survivors (validated strategies) and produces a candidate
set that is:
  1. Deduplicated — fuzzy structural similarity removes near-clones
  2. Complexity-scored — each strategy gets a difficulty proxy score
  3. Model-diverse — balanced across source models
  4. Difficulty-stratified — spans low / medium / high complexity

The output candidate set is ready for a Swiss-system Elo tournament.

Usage:
    # Default: select 40 BattleSnake candidates from extracted strategies
    python scripts/inverse/revenge_bench/select_candidates.py --game BattleSnake

    # Custom count and explicit report location
    python scripts/inverse/revenge_bench/select_candidates.py --game BattleSnake \
        --count 50 --output data/inverse/targets/battlesnake/selection_report.json

    # Dry-run: show what would be selected
    python scripts/inverse/revenge_bench/select_candidates.py --game BattleSnake --dry-run

    # Populate pool from selection (selection_report.json saved automatically)
    python scripts/inverse/revenge_bench/select_candidates.py --game BattleSnake \
        --count 40 --populate data/inverse/targets/battlesnake
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import logging
import math
import shutil
import sys
import tempfile
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from random import Random

# Ensure sibling modules are importable when running from repo root
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from revenge_bench.paths import REPO_ROOT as _PROJECT_ROOT

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from revenge_bench.scripts.inverse.codeclash_strategies.elo_tournament import (
    _default_game_args,
    make_pvp_config,
    run_match,
)
from revenge_bench.scripts.inverse.codeclash_strategies.validate_strategies import (
    discover_strategies,
    validate_all,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------


@dataclass
class StrategyProfile:
    """Profile of a single strategy with all computed metrics."""

    path: Path
    model: str
    tournament: str
    main_file: str

    # Content
    content: str = ""
    lines: int = 0

    # Similarity
    content_hash: str = ""  # MD5 of raw content
    feature_vector: dict = field(default_factory=dict)
    cluster_id: int = -1  # assigned during dedup

    # Complexity
    complexity_score: float = 0.0  # composite score 0–100
    complexity_tier: str = ""  # "low", "medium", "high"
    complexity_breakdown: dict = field(default_factory=dict)

    # Selection
    selected: bool = False
    selection_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "model": self.model,
            "tournament": self.tournament,
            "main_file": self.main_file,
            "lines": self.lines,
            "content_hash": self.content_hash,
            "cluster_id": self.cluster_id,
            "complexity_score": round(self.complexity_score, 2),
            "complexity_tier": self.complexity_tier,
            "complexity_breakdown": {
                k: round(v, 2) if isinstance(v, float) else v
                for k, v in self.complexity_breakdown.items()
            },
            "selected": self.selected,
            "selection_reason": self.selection_reason,
        }


# ---------------------------------------------------------------------------
# Abstract game-specific feature extractor
# ---------------------------------------------------------------------------


class FeatureExtractor(ABC):
    """Base class for game-specific code analysis.

    Subclass this for each game and register in ``GAME_EXTRACTORS``.
    """

    submission_file: str
    extension: str
    # Per-game default cosine similarity threshold for dedup.
    # Python-AST extractors produce rich feature vectors → high threshold.
    # Text-shingle extractors for C/Java/JS need the same high threshold
    # because shingles are high-dimensional and discriminative.
    default_similarity_threshold: float = 0.997

    @abstractmethod
    def extract_features(self, content: str) -> dict[str, float]:
        """Extract structural feature vector for similarity comparison."""

    @abstractmethod
    def compute_complexity(self, content: str) -> dict[str, float]:
        """Compute complexity metrics. Return dict with individual scores
        and a 'total' key with the composite score (0–100)."""

    def analyze(self, content: str) -> tuple[dict[str, float], dict[str, float]]:
        """Return ``(feature_vector, complexity_breakdown)`` in one call.

        The default implementation delegates to ``extract_features`` and
        ``compute_complexity`` separately.  Language-specific subclasses
        can override this to share a single parse pass.
        """
        features = self.extract_features(content)
        complexity = self.compute_complexity(content)
        return features, complexity

    def find_main_file(self, strategy_dir: Path) -> Path | None:
        """Locate the main strategy file."""
        main = strategy_dir / self.submission_file
        if main.is_file():
            return main
        # Fallback: prefer well-known entry-point names, then largest file
        candidates = [
            f
            for f in strategy_dir.iterdir()
            if f.is_file() and f.suffix == self.extension
        ]
        if not candidates:
            return None
        # Rank candidates: prioritise names that look like entry points
        _ENTRY_NAMES = {"main", "app", "server", "bot", "snake", "robot", "player"}

        def _rank(p: Path) -> tuple[int, int]:
            stem = p.stem.lower()
            return (0 if stem in _ENTRY_NAMES else 1, -p.stat().st_size)

        candidates.sort(key=_rank)
        return candidates[0]

    def list_auxiliary_files(self, strategy_dir: Path) -> list[Path]:
        """Return non-main source files that belong to this strategy.

        These are auxiliary modules the main file may import.  Only files
        with the game's expected extension are included; test/analysis
        scripts (filenames starting with ``test_``, ``analyze``,
        ``debug``, ``temp``) are excluded.
        """
        main = self.find_main_file(strategy_dir)
        if main is None:
            return []
        skip_prefixes = ("test_", "test.", "analyze", "debug", "temp", "__pycache__")
        aux: list[Path] = []
        for f in strategy_dir.iterdir():
            if not f.is_file() or f.suffix != self.extension:
                continue
            if f.name == main.name:
                continue
            if f.stem.lower().startswith(skip_prefixes):
                continue
            aux.append(f)
        return sorted(aux, key=lambda p: p.name)


# ---------------------------------------------------------------------------
# Per-game algorithm / strategy keyword patterns
# ---------------------------------------------------------------------------
# Each dict maps lowercased keyword → complexity weight.
# These are used for:
#   1. Feature vector: binary presence flag (for cosine-similarity dedup)
#   2. Complexity score: weighted sum (for tier assignment)
# Extra-feature-only patterns are only used in (1), not (2).

BATTLESNAKE_ALGO_PATTERNS: dict[str, int] = {
    "flood_fill": 2,
    "bfs": 2,
    "breadth_first": 2,
    "a_star": 3,
    "astar": 3,
    "dijkstra": 3,
    "voronoi": 4,
    "minimax": 4,
    "alpha_beta": 5,
    "monte_carlo": 5,
    "dynamic_program": 4,
    "memoiz": 2,
    "priority_queue": 2,
    "heapq": 2,
}
BATTLESNAKE_EXTRA_PATTERNS: list[str] = ["manhattan", "head_to_head", "deque"]

HUSKYBENCH_ALGO_PATTERNS: dict[str, int] = {
    # Hand evaluation
    "hand_strength": 2,
    "hand_rank": 2,
    "hand_eval": 2,
    "evaluate_hand": 2,
    "hand_score": 2,
    # Betting concepts
    "pot_odds": 3,
    "expected_value": 3,
    "ev_calc": 3,
    "equity": 3,
    "outs": 2,
    "implied_odds": 3,
    # Strategic patterns
    "bluff": 2,
    "semi_bluff": 3,
    "check_raise": 3,
    "slow_play": 3,
    "continuation_bet": 3,
    "c_bet": 3,
    "three_bet": 3,
    "board_texture": 3,
    # Position & style
    "position": 1,
    "early_position": 2,
    "late_position": 2,
    "aggression": 2,
    "tight": 1,
    "loose": 1,
    # Advanced
    "kelly": 4,
    "game_theory": 4,
    "nash": 4,
    "gto": 4,
    "opponent_model": 3,
    "exploit": 3,
    "range": 1,
    "hand_range": 3,
}
HUSKYBENCH_EXTRA_PATTERNS: list[str] = [
    "preflop",
    "postflop",
    "pre_flop",
    "post_flop",
    "fold",
    "raise",
    "all_in",
    "flush",
    "straight",
    "pair",
    "trips",
]

ROBOTRUMBLE_ALGO_PATTERNS: dict[str, int] = {
    "formation": 3,
    "flanking": 3,
    "surround": 3,
    "focus_fire": 3,
    "focusfire": 3,
    "force_ratio": 3,
    "forceratio": 3,
    "retreat": 2,
    "regroup": 2,
    "tactical": 2,
    "strategic": 2,
    "convergence": 3,
    "coordination": 3,
    "isolat": 2,
    "priority": 2,
    "aggression": 2,
    "defensive": 2,
    "minby": 1,
    "maxby": 1,
}
ROBOTRUMBLE_EXTRA_PATTERNS: list[str] = ["heal", "defend", "attack", "scout"]

# Strategy patterns for non-Python games (used in complexity scoring)
HALITE_STRATEGY_PATTERNS: dict[str, int] = {
    "expansion": 2,
    "border": 1,
    "frontier": 2,
    "production": 1,
    "strength": 1,
    "flood": 3,
    "pathfinding": 3,
    "combat": 2,
    "capture": 2,
    "heuristic": 2,
    "optimize": 2,
    "greedy": 1,
    "territory": 2,
}

ROBOCODE_STRATEGY_PATTERNS: dict[str, int] = {
    "wave_surfing": 4,
    "wavesurfing": 4,
    "linear_targeting": 3,
    "lineartargeting": 3,
    "circular_targeting": 4,
    "circulartargeting": 4,
    "pattern_matching": 4,
    "patternmatching": 4,
    "guess_factor": 4,
    "guessfactor": 4,
    "energy_drop": 2,
    "energydrop": 2,
    "predictive": 2,
    "intercept": 2,
    "anti_gravity": 4,
    "antigravity": 4,
    "minimum_risk": 3,
    "minimumrisk": 3,
    "wall_smooth": 3,
    "wallsmooth": 3,
    "segmentation": 3,
    "virtual_bullet": 3,
}


# ---------------------------------------------------------------------------
# Text shingle features (for non-AST languages: C, Java, JS)
# ---------------------------------------------------------------------------


def _text_shingle_features(
    content: str,
    shingle_size: int = 3,
    num_buckets: int = 64,
) -> dict[str, float]:
    """Create shingle-based features via feature hashing for similarity.

    Groups consecutive non-empty, non-comment lines into sliding windows
    of ``shingle_size``, hashes each window, and maps it into one of
    ``num_buckets`` fixed buckets.  This produces a **dense** fixed-dimension
    vector (unlike one-feature-per-shingle which is extremely sparse).

    Two strategies sharing many code lines will hash into the same buckets
    and have high cosine similarity.  Different strategies will have
    different bucket distributions.
    """
    # Normalise: strip whitespace, skip blanks and pure-comment lines
    lines = []
    for raw in content.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        # Skip C/Java/JS single-line comments and Redcode comments
        if stripped.startswith("//") or stripped.startswith(";"):
            continue
        # Collapse whitespace so formatting differences don't matter
        lines.append(" ".join(stripped.split()))

    # Initialise all buckets to 0 so every vector has the same dimensions
    features: dict[str, float] = {f"sh_{i}": 0.0 for i in range(num_buckets)}
    for i in range(max(1, len(lines) - shingle_size + 1)):
        shingle = "\n".join(lines[i : i + shingle_size])
        h = int(hashlib.md5(shingle.encode()).hexdigest(), 16)
        bucket = h % num_buckets
        features[f"sh_{bucket}"] += 1.0
    return features


# ---------------------------------------------------------------------------
# Python analysis (unified: single AST parse for features + complexity)
# ---------------------------------------------------------------------------

_DS_KEYWORDS = [
    "deque",
    "defaultdict",
    "Counter",
    "heapq",
    "namedtuple",
    "dataclass",
    "set(",
    "frozenset",
]


def _analyze_python(
    content: str,
    algo_patterns: dict[str, int] | None = None,
    extra_feature_patterns: list[str] | None = None,
) -> tuple[dict[str, float] | None, dict[str, float]]:
    """Single-pass analysis of Python source code.

    Parameters
    ----------
    content : str
        Python source code.
    algo_patterns : dict, optional
        Game-specific algorithm keyword → weight mapping.
        When *None*, no algorithm keywords are scored.
    extra_feature_patterns : list, optional
        Additional keywords that are recorded in the feature vector
        (for dedup similarity) but do NOT contribute to the complexity
        score.  When *None*, none are used.

    Returns ``(feature_vector, complexity_breakdown)``.
    """
    if algo_patterns is None:
        algo_patterns = {}
    if extra_feature_patterns is None:
        extra_feature_patterns = []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None, {"total": 0, "error": "SyntaxError"}

    loc = len(content.splitlines())
    lower = content.lower()

    # ------------------------------------------------------------------
    # Single AST walk — collect everything we need
    # ------------------------------------------------------------------
    features: dict[str, float] = Counter()
    func_count = 0
    branch_count = 0  # if / for / while / try
    node_count = 0

    for node in ast.walk(tree):
        node_count += 1
        features[f"node_{type(node).__name__}"] += 1

        if isinstance(node, ast.FunctionDef):
            func_count += 1
            features["func_count"] += 1
            features[f"func_args_{len(node.args.args)}"] += 1
        elif isinstance(node, ast.If):
            branch_count += 1
            features["if_count"] += 1
        elif isinstance(node, ast.For):
            branch_count += 1
            features["for_count"] += 1
        elif isinstance(node, ast.While):
            branch_count += 1
            features["while_count"] += 1
        elif isinstance(node, ast.Try):
            branch_count += 1
            features["try_count"] += 1
        elif isinstance(node, ast.Call):
            features["call_count"] += 1
            if isinstance(node.func, ast.Name):
                features[f"calls_{node.func.id}"] += 1
        elif isinstance(node, ast.Return):
            features["return_count"] += 1
        elif isinstance(node, ast.ListComp):
            features["listcomp_count"] += 1
        elif isinstance(node, ast.DictComp):
            features["dictcomp_count"] += 1

    # ------------------------------------------------------------------
    # Algorithm keyword patterns (single scan of lowered source)
    # ------------------------------------------------------------------
    algorithm_score = 0
    algos_found: list[str] = []
    for pat, weight in algo_patterns.items():
        if pat in lower:
            features[f"pattern_{pat}"] = 1
            algorithm_score += weight
            algos_found.append(pat)

    # Extra feature-only patterns (not weighted in complexity)
    for extra_pat in extra_feature_patterns:
        if extra_pat in lower and f"pattern_{extra_pat}" not in features:
            features[f"pattern_{extra_pat}"] = 1

    features["loc"] = loc

    # ------------------------------------------------------------------
    # Complexity-only metrics
    # ------------------------------------------------------------------
    max_depth = _max_nesting_depth(tree)

    ds_score = sum(1 for ds in _DS_KEYWORDS if ds in content)

    # Composite score (0-100)
    total = min(
        min(loc / 6, 25)  # LOC: 0-25 (caps at 150 lines)
        + min(func_count / 0.8, 20)  # Functions: 0-20 (caps at 16)
        + min(max_depth / 2, 15)  # Nesting: 0-15 (caps at depth 10)
        + min(branch_count / 2, 15)  # Branches: 0-15 (caps at 30)
        + min(algorithm_score * 2, 15)  # Algorithms: 0-15
        + min(ds_score * 2, 10),  # Data structures: 0-10
        100,
    )

    complexity = {
        "total": total,
        "loc": loc,
        "func_count": func_count,
        "max_nesting_depth": max_depth,
        "branch_count": branch_count,
        "node_count": node_count,
        "algorithm_score": algorithm_score,
        "algorithms_found": algos_found,
        "data_structure_score": ds_score,
    }

    return dict(features), complexity


# Thin wrappers kept for backward compatibility / standalone use.


def _python_features(content: str) -> dict[str, float] | None:
    """Extract feature vector for similarity comparison (delegates to ``_analyze_python``)."""
    feats, _ = _analyze_python(content)
    return feats


def _python_complexity(content: str) -> dict[str, float]:
    """Compute complexity breakdown (delegates to ``_analyze_python``)."""
    _, complexity = _analyze_python(content)
    return complexity


def _max_nesting_depth(tree: ast.AST) -> int:
    """Compute maximum nesting depth of control flow statements."""

    def _depth(node: ast.AST, current: int = 0) -> int:
        max_d = current
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                max_d = max(max_d, _depth(child, current + 1))
            else:
                max_d = max(max_d, _depth(child, current))
        return max_d

    return _depth(tree)


# ---------------------------------------------------------------------------
# Per-game extractors
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Per-game extractors
# ---------------------------------------------------------------------------


class _PythonExtractorMixin:
    """Shared ``analyze`` for all Python-based games (single AST parse).

    Subclasses set ``_algo_patterns`` and ``_extra_feature_patterns`` to
    inject game-specific keyword detection.
    """

    _algo_patterns: dict[str, int] = {}  # overridden by each subclass
    _extra_feature_patterns: list[str] = []  # overridden by each subclass

    def analyze(self, content: str) -> tuple[dict[str, float], dict[str, float]]:
        feats, complexity = _analyze_python(
            content,
            self._algo_patterns,
            self._extra_feature_patterns,
        )
        return feats if feats else {}, complexity

    def extract_features(self, content: str) -> dict[str, float]:
        feats, _ = _analyze_python(
            content,
            self._algo_patterns,
            self._extra_feature_patterns,
        )
        return feats if feats else {}

    def compute_complexity(self, content: str) -> dict[str, float]:
        _, complexity = _analyze_python(
            content,
            self._algo_patterns,
            self._extra_feature_patterns,
        )
        return complexity


class BattleSnakeExtractor(_PythonExtractorMixin, FeatureExtractor):
    submission_file = "main.py"
    extension = ".py"
    _algo_patterns = BATTLESNAKE_ALGO_PATTERNS
    _extra_feature_patterns = BATTLESNAKE_EXTRA_PATTERNS


class CoreWarExtractor(FeatureExtractor):
    submission_file = "warrior.red"
    extension = ".red"

    OPCODES = {
        "MOV",
        "ADD",
        "SUB",
        "MUL",
        "DIV",
        "MOD",
        "JMP",
        "JMZ",
        "JMN",
        "DJN",
        "CMP",
        "SEQ",
        "SNE",
        "SLT",
        "SPL",
        "DAT",
        "NOP",
        "LDP",
        "STP",
    }

    # Strategy archetypes detected via keyword patterns
    _STRATEGY_PATTERNS: dict[str, int] = {
        "scanner": 2,
        "bomber": 2,
        "stone": 2,
        "imp": 1,
        "replicat": 3,
        "vampire": 3,
        "spiral": 2,
        "carpet": 2,
        "quickscan": 3,
        "oneshot": 2,
        "silk": 2,
        "paper": 1,
    }

    def analyze(self, content: str) -> tuple[dict[str, float], dict[str, float]]:
        """Single-pass analysis of Redcode."""
        lines = [
            l.strip()
            for l in content.splitlines()
            if l.strip() and not l.strip().startswith(";")
        ]
        loc = len(lines)
        upper_content = content.upper()
        lower_content = content.lower()

        # --- Features (for similarity dedup) ---
        features: dict[str, float] = Counter()
        # Use binary presence (not raw counts) so shingles dominate cosine
        features["has_loc"] = 1 if loc > 0 else 0
        instr_count = 0
        unique_ops: set[str] = set()

        for line in lines:
            tokens = line.split()
            for tok in tokens[:2]:
                # Strip modifier (.f, .i, .a, .b, .ab, .ba, .x) and trailing comma
                upper = tok.upper().rstrip(",").split(".")[0]
                if upper in self.OPCODES:
                    features[f"op_{upper}"] = 1  # binary presence
                    instr_count += 1
                    unique_ops.add(upper)
                    break

        # Strategy pattern features
        strategy_score = 0
        strategies_found: list[str] = []
        for pat, weight in self._STRATEGY_PATTERNS.items():
            if pat in lower_content:
                features[f"pattern_{pat}"] = 1
                strategy_score += weight
                strategies_found.append(pat)

        # Text-shingle features for structural diversity
        features.update(_text_shingle_features(content))

        # --- Complexity ---
        has_spl = "SPL" in upper_content
        has_djn = "DJN" in upper_content
        has_sne = "SNE" in upper_content or "SEQ" in upper_content

        score = min(
            min(instr_count / 1.0, 30)
            + min(len(unique_ops) * 3, 30)
            + (10 if has_spl else 0)
            + (10 if has_djn else 0)
            + (10 if has_sne else 0)
            + min(loc / 2, 10),
            100,
        )

        complexity = {
            "total": score,
            "loc": loc,
            "instruction_count": instr_count,
            "unique_opcodes": len(unique_ops),
            "has_spl": has_spl,
            "has_djn": has_djn,
            "has_sne": has_sne,
            "strategy_score": strategy_score,
            "strategies_found": strategies_found,
        }
        return dict(features), complexity

    def extract_features(self, content: str) -> dict[str, float]:
        feats, _ = self.analyze(content)
        return feats

    def compute_complexity(self, content: str) -> dict[str, float]:
        _, complexity = self.analyze(content)
        return complexity


class HaliteExtractor(FeatureExtractor):
    submission_file = "main.c"
    extension = ".c"

    _STRATEGY_PATTERNS = HALITE_STRATEGY_PATTERNS
    _C_KEYWORDS = ["if", "for", "while", "switch", "struct", "malloc", "free"]
    _API_FUNCS = ["GetInit", "SendInit", "GetFrame", "SendFrame"]

    def analyze(self, content: str) -> tuple[dict[str, float], dict[str, float]]:
        """Single-pass analysis of C code."""
        loc = len(content.splitlines())
        lower = content.lower()

        # --- Features (binary presence, so shingles dominate cosine) ---
        features: dict[str, float] = Counter()
        features["has_loc"] = 1 if loc > 0 else 0
        for kw in self._C_KEYWORDS:
            features[f"kw_{kw}"] = (
                1 if (f" {kw} " in content or f" {kw}(" in content) else 0
            )
        for fn in self._API_FUNCS:
            features[f"api_{fn}"] = 1 if fn in content else 0

        # Strategy pattern features
        strategy_score = 0
        strategies_found: list[str] = []
        for pat, weight in self._STRATEGY_PATTERNS.items():
            if pat in lower:
                features[f"pattern_{pat}"] = 1
                strategy_score += weight
                strategies_found.append(pat)

        # Text-shingle features for structural diversity
        features.update(_text_shingle_features(content))

        # --- Complexity (uses raw counts, not affected by binary features) ---
        branches = content.count(" if ") + content.count(" if(")
        loops = (
            content.count(" for ")
            + content.count(" for(")
            + content.count(" while ")
            + content.count(" while(")
        )
        funcs = (
            content.count("\nint ")
            + content.count("\nvoid ")
            + content.count("\nfloat ")
        )

        score = min(
            min(loc / 5, 25)
            + min(branches, 20)
            + min(loops * 2, 15)
            + min(funcs * 3, 20)
            + min(strategy_score * 2, 20),
            100,
        )

        complexity = {
            "total": score,
            "loc": loc,
            "branch_count": branches,
            "loop_count": loops,
            "func_count": funcs,
            "strategy_score": strategy_score,
            "strategies_found": strategies_found,
        }
        return dict(features), complexity

    def extract_features(self, content: str) -> dict[str, float]:
        feats, _ = self.analyze(content)
        return feats

    def compute_complexity(self, content: str) -> dict[str, float]:
        _, complexity = self.analyze(content)
        return complexity


class HuskyBenchExtractor(_PythonExtractorMixin, FeatureExtractor):
    submission_file = "player.py"
    extension = ".py"
    _algo_patterns = HUSKYBENCH_ALGO_PATTERNS
    _extra_feature_patterns = HUSKYBENCH_EXTRA_PATTERNS


class RoboCodeExtractor(FeatureExtractor):
    submission_file = "MyTank.java"
    extension = ".java"

    _STRATEGY_PATTERNS = ROBOCODE_STRATEGY_PATTERNS
    _JAVA_KEYWORDS = ["if", "for", "while", "switch", "try", "class", "new"]
    _EVENT_METHODS = [
        "onScannedRobot",
        "onHitWall",
        "onHitByBullet",
        "onBulletHit",
        "onRobotDeath",
    ]
    _API_METHODS = [
        "onScannedRobot",
        "onHitWall",
        "onHitByBullet",
        "onBulletHit",
        "onRobotDeath",
        "setTurnRadarRight",
        "setTurnGunRight",
    ]

    def analyze(self, content: str) -> tuple[dict[str, float], dict[str, float]]:
        """Single-pass analysis of Java RoboCode bot."""
        loc = len(content.splitlines())
        lower = content.lower()
        lines = content.splitlines()

        # --- Features (binary presence, so shingles dominate cosine) ---
        features: dict[str, float] = Counter()
        features["has_loc"] = 1 if loc > 0 else 0
        for kw in self._JAVA_KEYWORDS:
            features[f"kw_{kw}"] = (
                1 if (f" {kw} " in content or f" {kw}(" in content) else 0
            )
        for method in self._API_METHODS:
            features[f"method_{method}"] = 1 if method in content else 0

        # Strategy pattern features
        strategy_score = 0
        strategies_found: list[str] = []
        for pat, weight in self._STRATEGY_PATTERNS.items():
            if pat in lower:
                features[f"pattern_{pat}"] = 1
                strategy_score += weight
                strategies_found.append(pat)

        # Text-shingle features for structural diversity
        features.update(_text_shingle_features(content))

        # --- Complexity (uses raw counts, not affected by binary features) ---
        branches = content.count(" if ") + content.count(" if(")
        methods = len([l for l in lines if "void " in l or "double " in l])
        event_handlers = sum(1 for m in self._EVENT_METHODS if m in content)

        score = min(
            min(loc / 5, 20)
            + min(branches, 20)
            + min(methods * 3, 20)
            + min(event_handlers * 6, 20)
            + min(strategy_score * 2, 20),
            100,
        )

        complexity = {
            "total": score,
            "loc": loc,
            "branch_count": branches,
            "method_count": methods,
            "event_handler_count": event_handlers,
            "strategy_score": strategy_score,
            "strategies_found": strategies_found,
        }
        return dict(features), complexity

    def extract_features(self, content: str) -> dict[str, float]:
        feats, _ = self.analyze(content)
        return feats

    def compute_complexity(self, content: str) -> dict[str, float]:
        _, complexity = self.analyze(content)
        return complexity


class RobotRumbleExtractor(FeatureExtractor):
    submission_file = "robot.js"
    extension = ".js"

    _JS_KEYWORDS = [
        "if",
        "for",
        "while",
        "switch",
        "function",
        "return",
        "const",
        "let",
        "var",
    ]
    _STRATEGY_PATTERNS = ROBOTRUMBLE_ALGO_PATTERNS

    def find_main_file(self, strategy_dir: Path) -> Path | None:
        for name in ["robot.js", "robot.py"]:
            f = strategy_dir / name
            if f.is_file():
                return f
        return None

    def _is_python(self, content: str) -> bool:
        return content.strip().startswith("def ") or "def robot(" in content

    def analyze(self, content: str) -> tuple[dict[str, float], dict[str, float]]:
        if self._is_python(content):
            feats, complexity = _analyze_python(
                content,
                ROBOTRUMBLE_ALGO_PATTERNS,
                ROBOTRUMBLE_EXTRA_PATTERNS,
            )
            return feats if feats else {}, complexity
        return self._analyze_js(content)

    def _analyze_js(self, content: str) -> tuple[dict[str, float], dict[str, float]]:
        """Single-pass analysis of JavaScript robot code."""
        loc = len(content.splitlines())
        lower = content.lower()

        # --- Features (binary presence, so shingles dominate cosine) ---
        features: dict[str, float] = Counter()
        features["has_loc"] = 1 if loc > 0 else 0
        for kw in self._JS_KEYWORDS:
            features[f"kw_{kw}"] = (
                1 if (f" {kw} " in content or f" {kw}(" in content) else 0
            )

        # Strategy pattern features
        strategy_score = 0
        strategies_found: list[str] = []
        for pat, weight in self._STRATEGY_PATTERNS.items():
            if pat in lower:
                features[f"pattern_{pat}"] = 1
                strategy_score += weight
                strategies_found.append(pat)

        # Text-shingle features for structural diversity
        features.update(_text_shingle_features(content))

        # --- Complexity (uses raw counts, not affected by binary features) ---
        branches = content.count(" if ") + content.count(" if(")
        loops = (
            content.count(" for ") + content.count(" for(") + content.count(" while ")
        )
        funcs = content.count("function ")

        score = min(
            min(loc / 5, 25)
            + min(branches, 20)
            + min(loops * 2, 15)
            + min(funcs * 3, 20)
            + min(strategy_score * 2, 20),
            100,
        )

        complexity = {
            "total": score,
            "loc": loc,
            "branch_count": branches,
            "loop_count": loops,
            "func_count": funcs,
            "strategy_score": strategy_score,
            "strategies_found": strategies_found,
        }
        return dict(features), complexity

    def extract_features(self, content: str) -> dict[str, float]:
        feats, _ = self.analyze(content)
        return feats

    def compute_complexity(self, content: str) -> dict[str, float]:
        _, complexity = self.analyze(content)
        return complexity


GAME_EXTRACTORS: dict[str, type[FeatureExtractor]] = {
    "BattleSnake": BattleSnakeExtractor,
    "CoreWar": CoreWarExtractor,
    "Halite": HaliteExtractor,
    "HuskyBench": HuskyBenchExtractor,
    "RoboCode": RoboCodeExtractor,
    "RobotRumble": RobotRumbleExtractor,
}


# ---------------------------------------------------------------------------
# Similarity & clustering
# ---------------------------------------------------------------------------


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Compute cosine similarity between two feature vectors."""
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def cluster_by_similarity(
    profiles: list[StrategyProfile],
    threshold: float = 0.98,
) -> list[list[int]]:
    """Greedy dedup: pick representatives that are all pairwise below threshold.

    Sorts strategies by complexity (descending) so higher-complexity strategies
    become representatives first. A strategy is a duplicate if it is within
    ``threshold`` cosine similarity of any existing representative.

    Returns list of clusters (each a list of indices into ``profiles``).
    The first element of each cluster is the representative.
    """
    n = len(profiles)
    # Sort by complexity descending so best strategies become reps
    order = sorted(range(n), key=lambda i: -profiles[i].complexity_score)

    clusters: list[list[int]] = []
    rep_indices: list[int] = []  # index into profiles for each cluster rep

    for idx in order:
        if not profiles[idx].feature_vector:
            # No features — treat as its own cluster
            clusters.append([idx])
            rep_indices.append(idx)
            continue

        # Check similarity against all existing representatives
        best_sim = 0.0
        best_cluster = -1
        for ci, ri in enumerate(rep_indices):
            if not profiles[ri].feature_vector:
                continue
            sim = cosine_similarity(
                profiles[idx].feature_vector, profiles[ri].feature_vector
            )
            if sim > best_sim:
                best_sim = sim
                best_cluster = ci

        if best_sim >= threshold and best_cluster >= 0:
            # Duplicate — add to existing cluster
            clusters[best_cluster].append(idx)
        else:
            # New representative
            clusters.append([idx])
            rep_indices.append(idx)

    return clusters


def pick_cluster_representative(
    cluster: list[int],
    profiles: list[StrategyProfile],
) -> int:
    """Pick the best representative from a cluster.

    The greedy clustering already places the highest-complexity strategy first,
    so we just return the first element.
    """
    return cluster[0]


# ---------------------------------------------------------------------------
# Stratified sampling
# ---------------------------------------------------------------------------


def assign_tiers(
    profiles: list[StrategyProfile],
    num_tiers: int = 3,
) -> None:
    """Assign complexity tiers based on percentile ranking."""
    scores = sorted(
        {p.complexity_score for p in profiles if p.selected or p.cluster_id >= 0}
    )
    if not scores:
        return

    tier_names = {0: "low", 1: "medium", 2: "high"}
    if num_tiers > 3:
        tier_names = {i: f"tier_{i}" for i in range(num_tiers)}

    for p in profiles:
        if p.complexity_score <= 0:
            p.complexity_tier = "low"
            continue
        # Percentile rank
        rank = sum(1 for s in scores if s <= p.complexity_score) / len(scores)
        tier_idx = min(int(rank * num_tiers), num_tiers - 1)
        p.complexity_tier = tier_names[tier_idx]


def select_diverse_stratified(
    profiles: list[StrategyProfile],
    count: int,
    *,
    seed: int = 42,
) -> list[int]:
    """Select strategies that are model-diverse and complexity-stratified.

    Within each model, strategies are binned into complexity tiers (low/med/high).
    Round-robin picks one from each model-tier combination until we reach count.
    """
    rng = Random(seed)

    # Group by (model, tier)
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, p in enumerate(profiles):
        if p.cluster_id < 0:
            continue  # filtered out
        buckets[(p.model, p.complexity_tier)].append(i)

    # Shuffle within each bucket
    for indices in buckets.values():
        rng.shuffle(indices)

    # Round-robin across all buckets
    selected: list[int] = []
    selected_set: set[int] = set()
    bucket_iters = {k: iter(v) for k, v in buckets.items()}

    # Sort buckets: cycle through models first, then tiers
    models = sorted({k[0] for k in buckets})
    tiers = ["low", "medium", "high"]
    bucket_order = [(m, t) for t in tiers for m in models if (m, t) in buckets]

    while len(selected) < count and bucket_iters:
        exhausted = []
        for key in bucket_order:
            if key not in bucket_iters:
                continue
            if len(selected) >= count:
                break
            try:
                idx = next(bucket_iters[key])
                if idx not in selected_set:
                    selected.append(idx)
                    selected_set.add(idx)
                    profiles[idx].selected = True
                    profiles[idx].selection_reason = f"round-robin {key[0]}/{key[1]}"
            except StopIteration:
                exhausted.append(key)
        for k in exhausted:
            del bucket_iters[k]
            bucket_order.remove(k)

    return selected


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_pipeline(
    source_dir: Path,
    game: str,
    count: int = 40,
    similarity_threshold: float | None = None,
    seed: int = 42,
    quiet: bool = False,
) -> tuple[list[StrategyProfile], list[int]]:
    """Run the full Round-2 selection pipeline.

    Returns (all_profiles, selected_indices).
    """
    if game not in GAME_EXTRACTORS:
        raise ValueError(f"Unknown game: {game}. Supported: {list(GAME_EXTRACTORS)}")

    extractor = GAME_EXTRACTORS[game]()

    # Use per-game default threshold when none is specified.
    if similarity_threshold is None:
        # Will be auto-calibrated after building profiles (Phase 1)
        similarity_threshold = extractor.default_similarity_threshold
        auto_calibrate = True
    else:
        auto_calibrate = False

    # -------------------------------------------------------------------------
    # Phase 0: Run Round-1 validation to get survivors
    # -------------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("Phase 0: Round-1 validation")
    logger.info("=" * 60)
    validation_results = validate_all(source_dir, game, quiet=True)
    passed_paths = {
        Path(r.strategy_path).resolve() for r in validation_results if r.passed
    }
    logger.info(f"  Round-1 survivors: {len(passed_paths)}")

    # -------------------------------------------------------------------------
    # Phase 1: Build profiles for all survivors
    # -------------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("Phase 1: Building strategy profiles")
    logger.info("=" * 60)

    profiles: list[StrategyProfile] = []

    # Reuse the same discovery logic as validate_strategies.py
    strategies = discover_strategies(source_dir, game)
    for s in strategies:
        model_dir = s["path"]
        if model_dir.resolve() not in passed_paths:
            continue

        main_file = extractor.find_main_file(model_dir)
        if main_file is None:
            continue

        content = main_file.read_text(errors="ignore")
        features, complexity = extractor.analyze(content)

        profile = StrategyProfile(
            path=model_dir,
            model=s["model"],
            tournament=s["tournament"],
            main_file=main_file.name,
            content=content,
            lines=len(content.splitlines()),
            content_hash=hashlib.md5(content.encode()).hexdigest()[:12],
            feature_vector=features,
            complexity_score=complexity.get("total", 0),
            complexity_breakdown=complexity,
        )
        profiles.append(profile)

    logger.info(f"  Profiles built: {len(profiles)}")

    # Model distribution
    model_counts = Counter(p.model for p in profiles)
    for model, cnt in model_counts.most_common():
        logger.info(f"    {model}: {cnt}")

    # -------------------------------------------------------------------------
    # Phase 1b: Auto-calibrate similarity threshold (if not explicitly set)
    # -------------------------------------------------------------------------
    if auto_calibrate and len(profiles) >= 10:
        import random as _rng

        _cal = _rng.Random(seed)
        n_prof = len(profiles)
        # Sample up to 2000 random pairs
        n_pairs = min(2000, n_prof * (n_prof - 1) // 2)
        pair_sims: list[float] = []
        seen_pairs: set[tuple[int, int]] = set()
        while len(pair_sims) < n_pairs:
            i = _cal.randrange(n_prof)
            j = _cal.randrange(n_prof)
            if i == j:
                continue
            key = (min(i, j), max(i, j))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            if profiles[i].feature_vector and profiles[j].feature_vector:
                sim = cosine_similarity(
                    profiles[i].feature_vector, profiles[j].feature_vector
                )
                pair_sims.append(sim)
        if pair_sims:
            pair_sims.sort()
            # Set threshold at p95 — dedup only the top 5% most-similar pairs
            p95_idx = int(len(pair_sims) * 0.95)
            calibrated = pair_sims[min(p95_idx, len(pair_sims) - 1)]
            logger.info(
                f"  Auto-calibrated threshold: {calibrated:.4f} "
                f"(p95 of {len(pair_sims)} sampled pairs, "
                f"median={pair_sims[len(pair_sims)//2]:.4f}, "
                f"max={pair_sims[-1]:.4f})"
            )
            similarity_threshold = calibrated

    # -------------------------------------------------------------------------
    # Phase 2: Fuzzy dedup via clustering
    # -------------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info(f"Phase 2: Fuzzy dedup (cosine threshold={similarity_threshold})")
    logger.info("=" * 60)

    clusters = cluster_by_similarity(profiles, threshold=similarity_threshold)
    logger.info(f"  Clusters formed: {len(clusters)}")

    # Pick one representative per cluster
    representatives: list[int] = []
    for cluster in clusters:
        rep = pick_cluster_representative(cluster, profiles)
        representatives.append(rep)
        for idx in cluster:
            profiles[idx].cluster_id = rep  # point to representative

    # Mark non-representatives
    rep_set = set(representatives)
    removed = len(profiles) - len(rep_set)
    logger.info(
        f"  Representatives: {len(rep_set)} (removed {removed} near-duplicates)"
    )

    # Only keep representatives for downstream
    for i, p in enumerate(profiles):
        if i not in rep_set:
            p.cluster_id = -1  # filtered out

    # Model distribution after dedup
    rep_models = Counter(profiles[i].model for i in representatives)
    for model, cnt in rep_models.most_common():
        logger.info(f"    {model}: {cnt}")

    # -------------------------------------------------------------------------
    # Phase 3: Complexity scoring & tier assignment
    # -------------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info("Phase 3: Complexity scoring & tier assignment")
    logger.info("=" * 60)

    assign_tiers(profiles)

    tier_counts = Counter(profiles[i].complexity_tier for i in representatives)
    logger.info(f"  Tier distribution: {dict(tier_counts)}")

    # Score stats
    rep_scores = [profiles[i].complexity_score for i in representatives]
    if rep_scores:
        logger.info(
            f"  Complexity: min={min(rep_scores):.1f}, "
            f"median={sorted(rep_scores)[len(rep_scores)//2]:.1f}, "
            f"max={max(rep_scores):.1f}"
        )

    # -------------------------------------------------------------------------
    # Phase 4: Stratified selection
    # -------------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info(
        f"Phase 4: Selecting {count} model-diverse, complexity-stratified candidates"
    )
    logger.info("=" * 60)

    selected = select_diverse_stratified(profiles, count, seed=seed)
    logger.info(f"  Selected: {len(selected)}")

    # Selection summary
    sel_models = Counter(profiles[i].model for i in selected)
    sel_tiers = Counter(profiles[i].complexity_tier for i in selected)
    logger.info(f"  By model: {dict(sel_models.most_common())}")
    logger.info(f"  By tier:  {dict(sel_tiers.most_common())}")

    if not quiet:
        logger.info("\n  Selected strategies:")
        for idx in selected:
            p = profiles[idx]
            algos = p.complexity_breakdown.get("algorithms_found", [])
            algo_str = f" [{', '.join(algos)}]" if algos else ""
            logger.info(
                f"    {p.model:30s}  score={p.complexity_score:5.1f}  "
                f"tier={p.complexity_tier:6s}  LOC={p.lines:3d}{algo_str}"
            )

    return profiles, selected


# ---------------------------------------------------------------------------
# Pool validation – self-play smoke test via PvP infrastructure
# ---------------------------------------------------------------------------


def _copy_strategy_to_pool(
    profile: StrategyProfile,
    dest: Path,
    game: str,
    extractor: FeatureExtractor,
) -> Path:
    """Copy a single strategy into the pool directory.

    Returns the created strategy directory path.
    """
    dir_name = f"{profile.model}__{profile.content_hash}"
    strategy_dir = dest / dir_name

    if strategy_dir.exists():
        return strategy_dir

    strategy_dir.mkdir(parents=True)

    # Copy main strategy file
    src = profile.path / profile.main_file
    shutil.copy2(src, strategy_dir / profile.main_file)

    # Copy auxiliary source files (modules the main file may import)
    for aux in extractor.list_auxiliary_files(profile.path):
        shutil.copy2(aux, strategy_dir / aux.name)
        logger.info(f"    + aux: {aux.name}")

    # Write provenance + complexity metadata
    meta = {
        "source": "codeclash_viewer",
        "game": game,
        "model": profile.model,
        "tournament": profile.tournament,
        "source_path": str(profile.path),
        "lines": profile.lines,
        "content_hash": profile.content_hash,
        "complexity_score": round(profile.complexity_score, 2),
        "complexity_tier": profile.complexity_tier,
        "complexity_breakdown": {
            k: round(v, 2) if isinstance(v, float) else v
            for k, v in profile.complexity_breakdown.items()
        },
    }
    (strategy_dir / "provenance.json").write_text(json.dumps(meta, indent=2))
    logger.info(f"  Copied: {dir_name}")
    return strategy_dir


# ---------------------------------------------------------------------------
# Game-specific static validators
# ---------------------------------------------------------------------------

# HuskyBench: Bot abstract methods that player.py's SimplePlayer must implement.
_HUSKYBENCH_REQUIRED_METHODS = {
    "on_start",
    "on_round_start",
    "get_action",
    "on_end_round",
    "on_end_game",
}

# HuskyBench: modules NOT available inside the Docker container.
_HUSKYBENCH_UNAVAILABLE_MODULES = {"hand_evaluator"}


def _static_check_huskybench(strategy_dir: Path) -> str | None:
    """Return an error reason string if the HuskyBench strategy is broken.

    Checks (all are static, no Docker needed):
    1. ``player.py`` must exist.
    2. ``SimplePlayer`` must be defined or aliased at module level.
    3. All abstract methods from ``Bot`` must be implemented.
    4. Must not import modules absent from the container.
    """
    player_file = strategy_dir / "player.py"
    if not player_file.exists():
        return "missing player.py"

    source = player_file.read_text(errors="ignore")

    # --- Check for SimplePlayer -----------------------------------------
    # Accept either ``class SimplePlayer`` or a module-level alias like
    # ``SimplePlayer = SomeOtherClass``.
    has_class = "class SimplePlayer" in source
    has_alias = bool(
        __import__("re").search(
            r"^SimplePlayer\s*=", source, __import__("re").MULTILINE
        )
    )
    if not has_class and not has_alias:
        return "no 'SimplePlayer' class or alias defined (game expects 'from player import SimplePlayer')"

    # --- Check required abstract methods --------------------------------
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"SyntaxError in player.py: {e}"

    # Collect all method names defined inside any class
    defined_methods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined_methods.add(node.name)

    missing = _HUSKYBENCH_REQUIRED_METHODS - defined_methods
    if missing:
        return f"missing required Bot methods: {', '.join(sorted(missing))}"

    # --- Check for unavailable imports ----------------------------------
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                if mod in _HUSKYBENCH_UNAVAILABLE_MODULES:
                    if not (strategy_dir / f"{mod}.py").exists():
                        return f"imports unavailable module '{mod}' (not in container, not in strategy dir)"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = node.module.split(".")[0]
                if mod in _HUSKYBENCH_UNAVAILABLE_MODULES:
                    if not (strategy_dir / f"{mod}.py").exists():
                        return f"imports unavailable module '{mod}' (not in container, not in strategy dir)"

    return None


# RobotRumble: identifiers declared with ``const`` in the game stdlib.
_ROBOTRUMBLE_STDLIB_CONSTS = {
    "SPAWN_COORDS",
    "SPAWN_COORDS_STRINGS",
    "HILL_COORDS",
    "HILL_COORDS_STRINGS",
    "MAP_SIZE",
    # Classes / functions (also top-level ``const``-like in strict mode)
    "Direction",
    "Coords",
    "Team",
    "ObjType",
    "Obj",
    "State",
    "ActionType",
    "Action",
}

# Regex: ``const <NAME>`` or ``let <NAME>`` at start of a line (ignoring
# leading whitespace) where <NAME> is one of the stdlib globals.
import re as _re

_ROBOTRUMBLE_REDECL_RE = _re.compile(
    r"^\s*(?:const|let)\s+("
    + "|".join(_re.escape(n) for n in _ROBOTRUMBLE_STDLIB_CONSTS)
    + r")\b",
    _re.MULTILINE,
)


def _static_check_robotrumble(strategy_dir: Path) -> str | None:
    """Return an error reason string if the RobotRumble strategy is broken.

    Checks for ``const`` / ``let`` redeclarations of game-engine globals
    defined in ``stdlib.js``.  This is a SyntaxError in strict-mode JS
    that the sandbox silently swallows (the bot simply never acts).
    """
    robot_file = strategy_dir / "robot.js"
    if not robot_file.exists():
        return "missing robot.js"

    source = robot_file.read_text(errors="ignore")
    m = _ROBOTRUMBLE_REDECL_RE.search(source)
    if m:
        return f"redeclares game global '{m.group(1)}' with const/let (SyntaxError in stdlib scope)"

    return None


# Registry mapping game names to their static checker.
_STATIC_VALIDATORS: dict[str, callable] = {
    "HuskyBench": _static_check_huskybench,
    "RobotRumble": _static_check_robotrumble,
}

# Games where Docker self-play ``valid_submit`` is reliable (no false-
# positive timeout issues).  For other games we rely on static checks only.
_DOCKER_VALID_SUBMIT_RELIABLE = {"BattleSnake", "CoreWar"}


# ---------------------------------------------------------------------------
# Pool validation
# ---------------------------------------------------------------------------


def validate_pool(
    pool_dir: Path,
    game: str,
    *,
    sims: int = 1,
    remove_broken: bool = True,
) -> list[dict]:
    """Validate every strategy in the pool.

    Runs two layers of checks:

    1. **Static analysis** — game-specific checks (HuskyBench: missing
       methods / bad imports; RobotRumble: const redeclarations).  Fast,
       no Docker, no false positives.
    2. **Docker self-play** — spins up the real game engine (strategy vs
       itself, 1 sim).  Catches crashes that static analysis can't see
       (e.g. BattleSnake import errors, CoreWar malformed Redcode).
       The ``valid_submit`` metadata flag is only used for games where
       it is known to be reliable (BattleSnake, CoreWar).

    Args:
        pool_dir: Directory containing strategy sub-directories.
        game: Game name (e.g. ``"BattleSnake"``).
        sims: Number of simulations per validation match (default 1).
        remove_broken: If True, delete broken strategy dirs from pool.

    Returns:
        List of dicts describing broken strategies (name, reason).
    """
    game_args = _default_game_args(game)
    broken: list[dict] = []
    static_checker = _STATIC_VALIDATORS.get(game)
    check_valid_submit = game in _DOCKER_VALID_SUBMIT_RELIABLE

    strategy_dirs = sorted(
        d for d in pool_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )

    logger.info("=" * 60)
    logger.info(f"Pool validation: {len(strategy_dirs)} strategies ({game})")
    logger.info("=" * 60)

    # --- Phase 1: Static checks (fast, no Docker) -----------------------
    static_broken_names: set[str] = set()
    if static_checker:
        logger.info(f"  Phase 1: static analysis ({game})")
        for strat_dir in strategy_dirs:
            name = strat_dir.name
            reason = static_checker(strat_dir)
            if reason:
                logger.warning(f"    BROKEN (static): {name}: {reason}")
                broken.append({"name": name, "reason": f"[static] {reason}"})
                static_broken_names.add(name)

        if static_broken_names:
            logger.warning(f"  Static: {len(static_broken_names)} broken")
        else:
            logger.info("  Static: all OK")

    # --- Phase 2: Docker self-play (slower, catches runtime crashes) ----
    logger.info("  Phase 2: Docker self-play validation")

    with tempfile.TemporaryDirectory(prefix="pool_validate_") as tmp:
        tmp_root = Path(tmp)

        docker_dirs = [d for d in strategy_dirs if d.name not in static_broken_names]
        for i, strat_dir in enumerate(docker_dirs, 1):
            name = strat_dir.name
            logger.info(f"  [{i}/{len(docker_dirs)}] Validating {name} …")

            config = make_pvp_config(
                game_name=game,
                sims_per_round=sims,
                player1_name=f"{name}_a",
                player1_path=str(strat_dir),
                player2_name=f"{name}_b",
                player2_path=str(strat_dir),
                game_args=game_args,
            )

            match_dir = tmp_root / name
            result = run_match(config, match_dir)

            if result is None:
                reason = "match returned None (container crash or timeout)"
                logger.warning(f"    BROKEN: {reason}")
                broken.append({"name": name, "reason": reason})
                continue

            # Check metadata for error traces and invalid submissions
            meta_file = match_dir / "metadata.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text())
                    round_stats = meta.get("round_stats", {}).get("0", {})

                    # Check explicit error list
                    errors = round_stats.get("errors", [])
                    if errors:
                        reason = f"runtime errors: {errors[0][:200]}"
                        logger.warning(f"    BROKEN: {reason}")
                        broken.append({"name": name, "reason": reason})
                        continue

                    # Check player_stats valid_submit — only for games
                    # where this flag is reliable (no false positives).
                    if check_valid_submit:
                        player_stats = round_stats.get("player_stats", {})
                        if player_stats:
                            invalid_players = [
                                (pn, pd.get("invalid_reason", "unknown"))
                                for pn, pd in player_stats.items()
                                if pd.get("valid_submit") is False
                            ]
                            if len(invalid_players) == 2:
                                reason = invalid_players[0][1][:200]
                                logger.warning(
                                    f"    BROKEN (invalid submission): {reason}"
                                )
                                broken.append({"name": name, "reason": reason})
                                continue

                except (json.JSONDecodeError, KeyError):
                    pass

            logger.info("    OK")

    # Report
    if broken:
        logger.warning(
            f"\nValidation: {len(broken)}/{len(strategy_dirs)} strategies BROKEN"
        )
        for b in broken:
            logger.warning(f"  ✗ {b['name']}: {b['reason']}")

        if remove_broken:
            for b in broken:
                bad_dir = pool_dir / b["name"]
                if bad_dir.exists():
                    shutil.rmtree(bad_dir)
                    logger.info(f"  Removed: {b['name']}")
            remaining = sum(1 for d in pool_dir.iterdir() if d.is_dir())
            logger.info(f"  Pool now has {remaining} strategies")
    else:
        logger.info(f"\nValidation: all {len(strategy_dirs)} strategies OK ✓")

    return broken


def populate_and_validate(
    profiles: list[StrategyProfile],
    selected: list[int],
    dest: Path,
    game: str,
    extractor: FeatureExtractor,
    *,
    validate: bool = True,
    target_count: int | None = None,
) -> tuple[list[int], list[dict]]:
    """Populate pool, validate via self-play, and backfill broken slots.

    1. Copy ``selected`` strategies into *dest*.
    2. Run ``validate_pool`` (self-play smoke test in Docker).
    3. If any strategies are broken, remove them and replace with the
       next-best candidate from the remaining deduped pool.
    4. Validate replacements too — repeat until stable or out of spares.

    Args:
        profiles: Full list of strategy profiles from the pipeline.
        selected: Indices into *profiles* for the initially-selected set.
        dest: Pool directory to populate.
        game: Game name.
        extractor: Feature extractor (for ``list_auxiliary_files``).
        validate: Whether to run Docker self-play validation.
        target_count: Desired pool size (default: ``len(selected)``).

    Returns:
        (final_selected, all_broken) — updated selected indices and
        cumulative list of broken strategy dicts.
    """
    if target_count is None:
        target_count = len(selected)

    dest.mkdir(parents=True, exist_ok=True)
    logger.info(f"\nPopulating pool: {dest}")

    # Build the full spare list: all deduped representatives NOT in selected,
    # ordered by complexity score (best first).
    selected_set = set(selected)
    spares = sorted(
        [
            i
            for i, p in enumerate(profiles)
            if p.cluster_id >= 0 and i not in selected_set
        ],
        key=lambda i: -profiles[i].complexity_score,
    )

    # Copy initial selection
    current_selected = list(selected)
    for idx in current_selected:
        _copy_strategy_to_pool(profiles[idx], dest, game, extractor)

    pool_size = sum(1 for d in dest.iterdir() if d.is_dir())
    logger.info(f"Pool: {pool_size} strategies in {dest}")

    if not validate:
        logger.info("  Skipping self-play validation (--no-validate)")
        return current_selected, []

    # Validate → remove broken → backfill → re-validate replacements
    all_broken: list[dict] = []
    max_backfill_rounds = 3  # safety cap

    for round_num in range(max_backfill_rounds + 1):
        broken = validate_pool(dest, game, sims=1, remove_broken=True)
        if not broken:
            break
        all_broken.extend(broken)

        # Map broken dir names back to profile indices
        broken_names = {b["name"] for b in broken}
        current_selected = [
            idx
            for idx in current_selected
            if f"{profiles[idx].model}__{profiles[idx].content_hash}"
            not in broken_names
        ]

        # How many slots to fill?
        need = target_count - sum(1 for d in dest.iterdir() if d.is_dir())
        if need <= 0 or not spares:
            if need > 0:
                logger.warning(
                    f"  Need {need} replacements but no more spares available"
                )
            break

        # Pick replacements from spares
        replacements = spares[:need]
        spares = spares[need:]
        logger.info(
            f"\n  Backfilling {len(replacements)} replacement(s) "
            f"(round {round_num + 1})"
        )

        for idx in replacements:
            p = profiles[idx]
            _copy_strategy_to_pool(p, dest, game, extractor)
            current_selected.append(idx)

        # Loop back to validate the new additions

    final_pool = sum(1 for d in dest.iterdir() if d.is_dir())
    if all_broken:
        logger.info(
            f"\nValidation summary: {len(all_broken)} broken removed, "
            f"pool: {final_pool}/{target_count}"
        )
    return current_selected, all_broken


def main():
    parser = argparse.ArgumentParser(
        description="Round 2: Dedup + complexity scoring + stratified selection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--game",
        type=str,
        default="BattleSnake",
        help=f"Game name (default: BattleSnake). Supported: {', '.join(GAME_EXTRACTORS)}",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/inverse/extracted_strategies"),
        help="Source directory with extracted strategies",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=40,
        help="Number of candidates to select (default: 40)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Cosine similarity threshold for dedup (default: per-game, typically 0.997)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Write JSON report to this file. When --populate is used without "
        "--output, the report is auto-saved as selection_report.json "
        "inside the populate directory.",
    )
    parser.add_argument(
        "--populate",
        type=Path,
        default=None,
        help="Copy selected strategies to this pool directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show selection without copying",
    )
    parser.add_argument(
        "--validate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run self-play validation on populated pool (default: on). "
        "Use --no-validate to skip. Requires Docker.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Minimal output",
    )

    args = parser.parse_args()

    profiles, selected = run_pipeline(
        args.source,
        args.game,
        count=args.count,
        similarity_threshold=args.threshold,
        seed=args.seed,
        quiet=args.quiet,
    )

    # Determine report output path
    report_path = args.output
    if report_path is None and args.populate and not args.dry_run:
        # Auto-save report inside the populate directory
        report_path = args.populate / "selection_report.json"

    # Write initial JSON report (before validation)
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "game": args.game,
            "source": str(args.source),
            "total_profiles": len(profiles),
            "after_dedup": sum(1 for p in profiles if p.cluster_id >= 0),
            "selected_count": len(selected),
            "selected": [profiles[i].to_dict() for i in selected],
            "all_profiles": [p.to_dict() for p in profiles],
        }
        report_path.write_text(json.dumps(report, indent=2))
        logger.info(f"\nReport written to {report_path}")

    # Populate pool directory + validate + backfill
    if args.populate and not args.dry_run:
        extractor = GAME_EXTRACTORS[args.game]()
        final_selected, all_broken = populate_and_validate(
            profiles,
            selected,
            args.populate,
            args.game,
            extractor,
            validate=args.validate,
            target_count=args.count,
        )

        # Amend report with validation results
        if all_broken and report_path:
            try:
                report = json.loads(report_path.read_text())
            except Exception:
                report = {}
            report["validation_broken"] = all_broken
            report["backfilled_count"] = len(final_selected) - len(
                [i for i in selected if i in final_selected]
            )
            report["pool_size_after_validation"] = sum(
                1 for d in args.populate.iterdir() if d.is_dir()
            )
            report["final_selected"] = [profiles[i].to_dict() for i in final_selected]
            report_path.write_text(json.dumps(report, indent=2))
            logger.info(f"Report updated with validation results: {report_path}")

    if not selected:
        sys.exit(1)


if __name__ == "__main__":
    main()
