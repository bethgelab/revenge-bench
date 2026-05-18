#!/usr/bin/env python3
"""Round-1 validation: hard filters for extracted CodeClash strategies.

Runs fast, offline checks (no simulation) to discard strategies that are
structurally broken.  Designed to be game-agnostic — each game registers a
``GameValidator`` that defines what a valid strategy looks like.

Usage:
    # Validate all extracted BattleSnake strategies
    python scripts/inverse/revenge_bench/validate_strategies.py --game BattleSnake

    # Only report failures (quiet mode)
    python scripts/inverse/revenge_bench/validate_strategies.py --game BattleSnake -q

    # Write results to JSON
    python scripts/inverse/revenge_bench/validate_strategies.py --game BattleSnake \
        --output data/inverse/validation_report.json

    # Validate a specific directory (e.g. an existing pool)
    python scripts/inverse/revenge_bench/validate_strategies.py --game BattleSnake \
        --source data/inverse/targets_v1/battlesnake

Checks performed (in order):
    1. main_file_exists  — the expected submission file is present
    2. min_lines         — file has ≥ N lines of code (default 10)
    3. syntax_valid      — file parses without errors (AST for Python, basic
                           checks for other languages)
    4. has_handlers      — required functions / patterns are defined
    5. has_entrypoint    — runtime entrypoint is present (e.g. run_server call)
    6. game_specific     — any extra per-game checks

A strategy must pass ALL checks to be considered valid.
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Result of a single validation check."""

    name: str
    passed: bool
    message: str = ""


@dataclass
class ValidationResult:
    """Aggregated validation result for one strategy."""

    strategy_path: str
    model: str
    tournament: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict:
        return {
            "strategy_path": self.strategy_path,
            "model": self.model,
            "tournament": self.tournament,
            "passed": self.passed,
            "checks": [
                {"name": c.name, "passed": c.passed, "message": c.message}
                for c in self.checks
            ],
        }


# ---------------------------------------------------------------------------
# Abstract game validator
# ---------------------------------------------------------------------------


class GameValidator(ABC):
    """Base class for game-specific validation logic.

    Subclass this for each game and register it in ``GAME_VALIDATORS``.
    """

    # The primary submission filename (e.g. "main.py", "warrior.red")
    submission_file: str
    # File extension for strategies (e.g. ".py", ".red")
    extension: str
    # Minimum lines of code to pass
    min_lines: int = 10

    @abstractmethod
    def check_syntax(self, content: str, filepath: Path) -> CheckResult:
        """Verify the file has no syntax errors."""

    @abstractmethod
    def check_handlers(self, content: str, filepath: Path) -> CheckResult:
        """Verify required functions / patterns are present."""

    @abstractmethod
    def check_entrypoint(self, content: str, filepath: Path) -> CheckResult:
        """Verify the runtime entrypoint exists."""

    def check_game_specific(self, content: str, filepath: Path) -> CheckResult | None:
        """Optional extra checks.  Return None to skip."""
        return None

    # ---- shared logic (not meant to be overridden) ----

    def validate(
        self, strategy_dir: Path, model: str, tournament: str
    ) -> ValidationResult:
        """Run all checks on a strategy directory."""
        result = ValidationResult(
            strategy_path=str(strategy_dir),
            model=model,
            tournament=tournament,
        )

        # 1. File exists
        filepath = strategy_dir / self.submission_file
        if not filepath.is_file():
            # Maybe the file has a different name but right extension
            candidates = [
                f
                for f in strategy_dir.iterdir()
                if f.is_file() and f.suffix == self.extension
            ]
            if candidates:
                filepath = candidates[0]
                result.checks.append(
                    CheckResult(
                        "main_file_exists",
                        True,
                        f"Expected {self.submission_file}, using {filepath.name}",
                    )
                )
            else:
                result.checks.append(
                    CheckResult(
                        "main_file_exists",
                        False,
                        f"No {self.extension} file found",
                    )
                )
                return result  # can't continue
        else:
            result.checks.append(CheckResult("main_file_exists", True))

        content = filepath.read_text(errors="ignore")

        # 2. Min lines
        lines = len(content.splitlines())
        if lines < self.min_lines:
            result.checks.append(
                CheckResult(
                    "min_lines",
                    False,
                    f"{lines} lines < minimum {self.min_lines}",
                )
            )
        else:
            result.checks.append(
                CheckResult(
                    "min_lines",
                    True,
                    f"{lines} lines",
                )
            )

        # 3. Syntax
        result.checks.append(self.check_syntax(content, filepath))

        # 4. Handlers
        result.checks.append(self.check_handlers(content, filepath))

        # 5. Entrypoint
        result.checks.append(self.check_entrypoint(content, filepath))

        # 6. Game-specific
        extra = self.check_game_specific(content, filepath)
        if extra is not None:
            result.checks.append(extra)

        return result


# ---------------------------------------------------------------------------
# Per-game validators
# ---------------------------------------------------------------------------


class BattleSnakeValidator(GameValidator):
    """Validator for BattleSnake Python strategies."""

    submission_file = "main.py"
    extension = ".py"
    min_lines = 30

    REQUIRED_HANDLERS = {"info", "start", "end", "move"}

    def check_syntax(self, content: str, filepath: Path) -> CheckResult:
        try:
            ast.parse(content, filename=str(filepath))
            return CheckResult("syntax_valid", True)
        except SyntaxError as e:
            return CheckResult(
                "syntax_valid", False, f"SyntaxError: {e.msg} (line {e.lineno})"
            )

    def check_handlers(self, content: str, filepath: Path) -> CheckResult:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return CheckResult("has_handlers", False, "Cannot parse — syntax error")

        # Collect top-level function names
        top_funcs = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }

        missing = self.REQUIRED_HANDLERS - top_funcs
        if missing:
            # Special case: some strategies use choose_move instead of move
            if missing == {"move"} and "choose_move" in top_funcs:
                return CheckResult(
                    "has_handlers",
                    True,
                    "Uses choose_move instead of move (needs wrapper)",
                )
            # Some strategies might not define info/start/end but still work
            # if they have move — mark as warning but pass if move exists
            if "move" in top_funcs or "choose_move" in top_funcs:
                return CheckResult(
                    "has_handlers",
                    True,
                    f"Missing {missing} but has move handler (stubs can be added)",
                )
            return CheckResult(
                "has_handlers",
                False,
                f"Missing required handlers: {missing}",
            )
        return CheckResult("has_handlers", True)

    def check_entrypoint(self, content: str, filepath: Path) -> CheckResult:
        has_main_guard = "__name__" in content and "__main__" in content
        has_run_server = "run_server(" in content

        if has_main_guard and has_run_server:
            return CheckResult("has_entrypoint", True)
        if has_main_guard and not has_run_server:
            return CheckResult(
                "has_entrypoint",
                False,
                "Has __main__ guard but no run_server() call",
            )
        if has_run_server and not has_main_guard:
            return CheckResult(
                "has_entrypoint",
                False,
                "Has run_server() but no __main__ guard",
            )
        return CheckResult(
            "has_entrypoint",
            False,
            "Missing if __name__ == '__main__': ... run_server(...)",
        )


class CoreWarValidator(GameValidator):
    """Validator for CoreWar Redcode strategies."""

    submission_file = "warrior.red"
    extension = ".red"
    min_lines = 3

    # Common Redcode opcodes
    REDCODE_OPCODES = {
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

    def check_syntax(self, content: str, filepath: Path) -> CheckResult:
        # Redcode is assembly-like; basic check: at least one valid opcode
        lines = [
            l.strip()
            for l in content.splitlines()
            if l.strip() and not l.strip().startswith(";")
        ]
        if not lines:
            return CheckResult("syntax_valid", False, "File is empty or all comments")

        found_opcode = False
        for line in lines:
            # Skip metadata lines (;redcode, ;name, ;author, etc.)
            tokens = line.split()
            if tokens and tokens[0].upper() in self.REDCODE_OPCODES:
                found_opcode = True
                break
            # Some lines have labels: "label  MOV ..."
            if len(tokens) > 1 and tokens[1].upper() in self.REDCODE_OPCODES:
                found_opcode = True
                break
        if not found_opcode:
            return CheckResult("syntax_valid", False, "No valid Redcode opcodes found")
        return CheckResult("syntax_valid", True)

    def check_handlers(self, content: str, filepath: Path) -> CheckResult:
        # Redcode doesn't have "handlers" — just needs executable instructions
        lines = [
            l.strip()
            for l in content.splitlines()
            if l.strip() and not l.strip().startswith(";")
        ]
        instruction_count = 0
        for line in lines:
            tokens = line.split()
            for tok in tokens[:2]:  # opcode can be first or second token
                if tok.upper() in self.REDCODE_OPCODES:
                    instruction_count += 1
                    break
        if instruction_count < 2:
            return CheckResult(
                "has_handlers",
                False,
                f"Only {instruction_count} instruction(s) — likely not a real warrior",
            )
        return CheckResult("has_handlers", True, f"{instruction_count} instructions")

    def check_entrypoint(self, content: str, filepath: Path) -> CheckResult:
        # CoreWar warriors are loaded directly by the MARS VM — no entrypoint
        # needed. But they should ideally have an ORG or END directive.
        content_upper = content.upper()
        has_org = bool(re.search(r"^\s*ORG\b", content_upper, re.MULTILINE))
        has_end = bool(re.search(r"^\s*END\b", content_upper, re.MULTILINE))
        if has_org or has_end:
            return CheckResult("has_entrypoint", True, "Has ORG/END directive")
        # Execution starts at first instruction — still valid
        return CheckResult(
            "has_entrypoint",
            True,
            "No ORG/END directive (execution starts at first instruction)",
        )


class HaliteValidator(GameValidator):
    """Validator for Halite C strategies."""

    submission_file = "main.c"
    extension = ".c"
    min_lines = 20

    def check_syntax(self, content: str, filepath: Path) -> CheckResult:
        # Basic C syntax checks — can't compile without a toolchain
        if "int main" not in content and "void main" not in content:
            return CheckResult("syntax_valid", False, "No main() function found")
        # Check for balanced braces (rough indicator)
        if content.count("{") != content.count("}"):
            return CheckResult(
                "syntax_valid",
                False,
                f"Unbalanced braces: {content.count('{')} open, {content.count('}')} close",
            )
        return CheckResult("syntax_valid", True)

    def check_handlers(self, content: str, filepath: Path) -> CheckResult:
        # Halite strategies need GetInit/SendInit/GetFrame/SendFrame
        required = ["GetInit", "SendInit", "GetFrame", "SendFrame"]
        # Alternative: some strategies use different APIs
        alt_required = ["getInit", "sendInit", "getFrame", "sendFrame"]

        found = [r for r in required if r in content]
        alt_found = [r for r in alt_required if r in content]

        if len(found) >= 3 or len(alt_found) >= 3:
            return CheckResult("has_handlers", True)

        # At minimum must have a game loop of some kind
        if "main" in content and ("while" in content or "for" in content):
            return CheckResult(
                "has_handlers",
                True,
                "Has main + loop (may use non-standard API)",
            )

        return CheckResult(
            "has_handlers",
            False,
            f"Missing Halite API calls. Found: {found or alt_found}",
        )

    def check_entrypoint(self, content: str, filepath: Path) -> CheckResult:
        # C programs run from main() — already checked in syntax
        if "int main" in content or "void main" in content:
            return CheckResult("has_entrypoint", True)
        return CheckResult("has_entrypoint", False, "No main() entrypoint")


class HuskyBenchValidator(GameValidator):
    """Validator for HuskyBench Python strategies (poker bot)."""

    submission_file = "player.py"
    extension = ".py"
    min_lines = 20

    def check_syntax(self, content: str, filepath: Path) -> CheckResult:
        try:
            ast.parse(content, filename=str(filepath))
            return CheckResult("syntax_valid", True)
        except SyntaxError as e:
            return CheckResult(
                "syntax_valid", False, f"SyntaxError: {e.msg} (line {e.lineno})"
            )

    def check_handlers(self, content: str, filepath: Path) -> CheckResult:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return CheckResult("has_handlers", False, "Cannot parse — syntax error")

        # Look for a class that extends Bot or has on_start method
        has_bot_class = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check if it inherits from Bot
                for base in node.bases:
                    base_name = ""
                    if isinstance(base, ast.Name):
                        base_name = base.id
                    elif isinstance(base, ast.Attribute):
                        base_name = base.attr
                    if "Bot" in base_name or "Player" in base_name:
                        has_bot_class = True
                        break
                # Also check method names
                methods = {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
                if "on_start" in methods or "get_action" in methods or "act" in methods:
                    has_bot_class = True

        if has_bot_class:
            return CheckResult("has_handlers", True)
        return CheckResult(
            "has_handlers", False, "No Bot subclass with game methods found"
        )

    def check_entrypoint(self, content: str, filepath: Path) -> CheckResult:
        # HuskyBench strategies are imported by the launcher, not run directly
        # The class itself IS the entrypoint — just needs to be importable
        return CheckResult("has_entrypoint", True, "Imported by launcher (class-based)")


class RoboCodeValidator(GameValidator):
    """Validator for RoboCode Java strategies."""

    submission_file = "MyTank.java"
    extension = ".java"
    min_lines = 15

    def check_syntax(self, content: str, filepath: Path) -> CheckResult:
        # Basic Java checks
        if "class " not in content:
            return CheckResult("syntax_valid", False, "No class definition found")
        if content.count("{") != content.count("}"):
            return CheckResult(
                "syntax_valid",
                False,
                f"Unbalanced braces: {content.count('{')} open, {content.count('}')} close",
            )
        return CheckResult("syntax_valid", True)

    def check_handlers(self, content: str, filepath: Path) -> CheckResult:
        has_run = bool(re.search(r"public\s+void\s+run\s*\(", content))
        if not has_run:
            return CheckResult(
                "has_handlers", False, "Missing public void run() method"
            )

        # Check for extends Robot / AdvancedRobot
        has_extends = bool(re.search(r"extends\s+(Advanced)?Robot\b", content))
        if not has_extends:
            return CheckResult(
                "has_handlers",
                False,
                "Class does not extend Robot or AdvancedRobot",
            )
        return CheckResult("has_handlers", True)

    def check_entrypoint(self, content: str, filepath: Path) -> CheckResult:
        # Robocode manages lifecycle — the class IS the entrypoint
        has_extends = bool(re.search(r"extends\s+(Advanced)?Robot\b", content))
        if has_extends:
            return CheckResult("has_entrypoint", True, "Managed by Robocode engine")
        return CheckResult("has_entrypoint", False, "Not a Robot subclass")


class RobotRumbleValidator(GameValidator):
    """Validator for RobotRumble JS/Python strategies."""

    submission_file = "robot.js"  # preferred; also accepts robot.py
    extension = ".js"
    min_lines = 5

    def validate(
        self, strategy_dir: Path, model: str, tournament: str
    ) -> ValidationResult:
        """Override to handle dual-language (JS or Python)."""
        # Try JS first, then Python
        js_file = strategy_dir / "robot.js"
        py_file = strategy_dir / "robot.py"

        if js_file.is_file():
            self.submission_file = "robot.js"
            self.extension = ".js"
        elif py_file.is_file():
            self.submission_file = "robot.py"
            self.extension = ".py"

        return super().validate(strategy_dir, model, tournament)

    def check_syntax(self, content: str, filepath: Path) -> CheckResult:
        if filepath.suffix == ".py":
            try:
                ast.parse(content, filename=str(filepath))
                return CheckResult("syntax_valid", True)
            except SyntaxError as e:
                return CheckResult(
                    "syntax_valid", False, f"SyntaxError: {e.msg} (line {e.lineno})"
                )
        # JS: basic checks
        if content.count("{") != content.count("}"):
            return CheckResult(
                "syntax_valid",
                False,
                f"Unbalanced braces: {content.count('{')} open, {content.count('}')} close",
            )
        return CheckResult("syntax_valid", True)

    def check_handlers(self, content: str, filepath: Path) -> CheckResult:
        if filepath.suffix == ".py":
            has_func = bool(re.search(r"def\s+robot\s*\(", content))
        else:
            has_func = bool(re.search(r"function\s+robot\s*\(", content))

        if has_func:
            return CheckResult("has_handlers", True)
        return CheckResult(
            "has_handlers",
            False,
            "Missing robot(state, unit) function",
        )

    def check_entrypoint(self, content: str, filepath: Path) -> CheckResult:
        # RobotRumble loads the file directly — function existence is enough
        return CheckResult("has_entrypoint", True, "Loaded by engine")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

GAME_VALIDATORS: dict[str, type[GameValidator]] = {
    "BattleSnake": BattleSnakeValidator,
    "CoreWar": CoreWarValidator,
    "Halite": HaliteValidator,
    "HuskyBench": HuskyBenchValidator,
    "RoboCode": RoboCodeValidator,
    "RobotRumble": RobotRumbleValidator,
}


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


def discover_strategies(source_dir: Path, game: str) -> list[dict]:
    """Discover strategy directories under source_dir.

    Supports two layouts:
      1. Extracted: {source_dir}/{Game}/{tournament}/final/{model}/
      2. Pool:      {source_dir}/{model}__{hash}/
    """
    strategies: list[dict] = []

    # Layout 1: extracted_strategies/{Game}/{tournament}/final/{model}/
    game_dir = source_dir / game
    if game_dir.is_dir():
        for tournament_dir in sorted(game_dir.iterdir()):
            final_dir = tournament_dir / "final"
            if not final_dir.is_dir():
                continue
            for model_dir in sorted(final_dir.iterdir()):
                if not model_dir.is_dir():
                    continue
                strategies.append(
                    {
                        "path": model_dir,
                        "model": model_dir.name,
                        "tournament": tournament_dir.name,
                    }
                )
        return strategies

    # Layout 2: pool directory — {model}__{hash}/
    for d in sorted(source_dir.iterdir()):
        if not d.is_dir():
            continue
        parts = d.name.split("__")
        model = parts[0] if len(parts) >= 2 else d.name
        strategies.append(
            {
                "path": d,
                "model": model,
                "tournament": "pool",
            }
        )

    return strategies


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def validate_all(
    source_dir: Path,
    game: str,
    *,
    quiet: bool = False,
) -> list[ValidationResult]:
    """Validate all strategies for a game.

    Returns list of ValidationResult objects.
    """
    if game not in GAME_VALIDATORS:
        raise ValueError(f"Unknown game: {game}. Supported: {list(GAME_VALIDATORS)}")

    validator = GAME_VALIDATORS[game]()
    strategies = discover_strategies(source_dir, game)

    if not strategies:
        logger.warning(f"No strategies found in {source_dir}")
        return []

    logger.info(f"Validating {len(strategies)} {game} strategies...")

    results: list[ValidationResult] = []
    pass_count = 0
    fail_count = 0

    for s in strategies:
        result = validator.validate(s["path"], s["model"], s["tournament"])
        results.append(result)

        if result.passed:
            pass_count += 1
            if not quiet:
                logger.info(f"  PASS  {s['model']} ({s['path'].name})")
        else:
            fail_count += 1
            failures = ", ".join(f"{c.name}: {c.message}" for c in result.failed_checks)
            logger.warning(f"  FAIL  {s['model']} ({s['path'].name}) — {failures}")

    # Summary
    total = pass_count + fail_count
    logger.info(f"\nResults: {pass_count}/{total} passed, {fail_count} failed")

    # Breakdown by failure reason
    if fail_count:
        from collections import Counter

        failure_reasons = Counter()
        for r in results:
            for c in r.failed_checks:
                failure_reasons[c.name] += 1
        logger.info("Failure breakdown:")
        for reason, count in failure_reasons.most_common():
            logger.info(f"  {reason}: {count}")

    # Breakdown by model
    from collections import defaultdict

    model_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"pass": 0, "fail": 0})
    for r in results:
        model_stats[r.model]["pass" if r.passed else "fail"] += 1
    logger.info("\nPer-model breakdown:")
    for model in sorted(model_stats):
        s = model_stats[model]
        logger.info(f"  {model}: {s['pass']} pass, {s['fail']} fail")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate extracted CodeClash strategies (Round 1: hard filters)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--game",
        type=str,
        default="BattleSnake",
        help="Game name (default: BattleSnake). Supported: "
        + ", ".join(GAME_VALIDATORS),
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/inverse/extracted_strategies"),
        help="Source directory (default: data/inverse/extracted_strategies)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Only show failures",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Write JSON report to this file",
    )

    args = parser.parse_args()

    results = validate_all(args.source, args.game, quiet=args.quiet)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "game": args.game,
            "source": str(args.source),
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "strategies": [r.to_dict() for r in results],
        }
        args.output.write_text(json.dumps(report, indent=2))
        logger.info(f"\nReport written to {args.output}")

    # Exit with non-zero if any failures
    if any(not r.passed for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
