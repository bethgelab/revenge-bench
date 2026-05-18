#!/usr/bin/env python3
"""
Extract strategies from downloaded CodeClash HTML artifacts.

Usage:
    python -m revenge_bench.scripts.inverse.codeclash_strategies.extract --input data/codeclash_html
"""

import argparse
import html
import json
import re
import shutil
from pathlib import Path

from bs4 import BeautifulSoup
from tqdm import tqdm


def extract_heredoc_code(text: str) -> dict[str, str]:
    """Extract code from heredoc patterns (cat <<'EOF' > file)."""
    files = {}
    decoded = html.unescape(text)

    # Pattern for heredoc with various file extensions
    heredoc_pattern = r"cat\s+<<'?EOF'?\s*>\s*(\S+\.(?:py|java|c|cpp|h|js|ts|red|asm))\s*\n(.*?)(?:\nEOF\b|\n```)"

    matches = re.findall(heredoc_pattern, decoded, re.DOTALL)

    for filename, code in matches:
        code = code.strip()
        if len(code) > 50:  # Skip tiny snippets
            files[filename] = code

    return files


def extract_from_html(
    html_file: Path, output_dir: Path, max_size_mb: float = 200
) -> int:
    """
    Extract strategies from a single HTML file.

    Returns:
        Number of players extracted, or -1 if skipped (too large)
    """
    file_size_mb = html_file.stat().st_size / (1024 * 1024)
    if file_size_mb > max_size_mb:
        return -1

    with open(html_file, encoding="utf-8", errors="ignore") as f:
        content = f.read()

    soup = BeautifulSoup(content, "html.parser")

    # Parse filename for game type
    parts = html_file.name.replace(".html", "").split(".")
    game_type = parts[1] if len(parts) > 1 else "unknown"
    match_id = html_file.name.replace(".html", "")

    # Find trajectory foldouts
    foldouts = soup.find_all("details", class_="trajectory-details-foldout")
    if not foldouts:
        return 0

    # Group by player
    players = {}
    for f in foldouts:
        player = f.get("data-player")
        round_num = f.get("data-round")
        if player and round_num:
            try:
                round_int = int(round_num)
                if player not in players:
                    players[player] = {}
                players[player][round_int] = f
            except ValueError:
                pass

    if not players:
        return 0

    match_dir = output_dir / game_type / match_id
    match_dir.mkdir(parents=True, exist_ok=True)

    count = 0

    for player, rounds in players.items():
        # Track final version of each file across all rounds
        final_files = {}

        for round_num in sorted(rounds.keys()):
            foldout = rounds[round_num]
            for pre in foldout.find_all("pre"):
                text = pre.get_text()
                files = extract_heredoc_code(text)
                for filename, code in files.items():
                    final_files[filename] = (round_num, code)

        if not final_files:
            continue

        # Shorten model names
        player_short = (
            player.replace("claude-sonnet-4-20250514", "cs4-20250514")
            .replace("claude-sonnet-4-5-20250929", "cs4-5-20250929")
            .replace("gpt-5-mini", "gpt5-mini")
            .replace("gpt-5", "gpt5")
        )

        player_dir = match_dir / "final" / player_short
        player_dir.mkdir(parents=True, exist_ok=True)

        for filename, (_round_num, code) in final_files.items():
            base = Path(filename).name
            with open(player_dir / base, "w") as f:
                f.write(code)

        # Save metadata
        with open(player_dir / "info.json", "w") as f:
            json.dump(
                {
                    "player": player,
                    "files": {Path(fn).name: rn for fn, (rn, _) in final_files.items()},
                },
                f,
                indent=2,
            )

        count += 1

    return count


def extract_strategies(
    input_dir: Path,
    output_dir: Path,
    max_size_mb: float = 200,
    clear_output: bool = False,
) -> dict:
    """
    Extract strategies from all HTML files in input directory.

    Args:
        input_dir: Directory containing downloaded HTML files
        output_dir: Where to save extracted strategies
        max_size_mb: Skip files larger than this (BeautifulSoup limit)
        clear_output: If True, delete output_dir before extracting

    Returns:
        dict with total extracted, skipped, errors
    """
    if clear_output and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_files = list(input_dir.glob("**/*.html"))
    print(f"Found {len(html_files)} HTML files")

    total = 0
    errors = []
    skipped = []

    for html_file in tqdm(html_files, desc="Extracting"):
        try:
            count = extract_from_html(html_file, output_dir, max_size_mb)
            if count == -1:
                file_size_mb = html_file.stat().st_size / (1024 * 1024)
                skipped.append(
                    {"file": html_file.name, "size_mb": round(file_size_mb, 1)}
                )
            else:
                total += count
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            errors.append((html_file.name, str(e)[:100]))

    print(f"\n✓ Extracted {total} player strategies")
    print(f"  Skipped {len(skipped)} large files (>{max_size_mb}MB)")

    if errors:
        print(f"  Errors: {len(errors)}")

    if skipped:
        with open(output_dir / "skipped_large_files.json", "w") as f:
            json.dump(skipped, f, indent=2)

    return {"total": total, "skipped": skipped, "errors": errors}


def main():
    parser = argparse.ArgumentParser(
        description="Extract strategies from CodeClash HTML"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/inverse/codeclash_html"),
        help="Input directory with HTML files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/inverse/extracted_strategies"),
        help="Output directory for extracted strategies",
    )
    parser.add_argument(
        "--max-size", type=float, default=200, help="Skip files larger than this (MB)"
    )
    parser.add_argument(
        "--clear", action="store_true", help="Clear output directory before extracting"
    )
    args = parser.parse_args()

    extract_strategies(args.input, args.output, args.max_size, args.clear)


if __name__ == "__main__":
    main()
