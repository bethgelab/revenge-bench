"""Generate OpenRouter-routed pool configs from the GPT-5 templates.

For each (model, game) pair, this reads configs/inverse/pool/gpt5/gpt5_<game>.yaml,
applies a small set of line-based substitutions, and writes the result to
configs/inverse/pool/<model_dir>/<model_dir>_<game>.yaml.

The transformations:
  - top-level `name: gpt5_full_pool` -> `name: <model_dir>_full_pool`
  - `model_name: openai/gpt-5`        -> `model_name: openrouter/<or_slug>`
  - drop the two local LLM proxy kwargs (`api_base: http://localhost:8000/v1`, `api_key: dummy`).
    Matches the existing deepseekv32 configs: LiteLLM auto-routes `openrouter/`
    to https://openrouter.ai/api/v1 and reads OPENROUTER_API_KEY from the env.
  - if model_kwargs ends up empty, replace its body with `{}` to keep YAML valid.
  - the trailing blank line that originally separated the model_kwargs block from
    the next list item is also consumed (harmless; the YAML remains valid).

Re-runnable: overwrites existing outputs. Note: removing a model from MODELS does
NOT delete its output directory; clean up manually if needed.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "configs" / "inverse" / "pool" / "gpt5"
DST_DIR = REPO_ROOT / "configs" / "inverse" / "pool"

GAMES = ["battlesnake", "halite", "huskybench", "robocode", "robotrumble"]

# (subdir_name, openrouter_slug)
MODELS: list[tuple[str, str]] = [
    ("gemma_4_26b_a4b",   "google/gemma-4-26b-a4b-it"),
    ("gemma_4_31b",       "google/gemma-4-31b-it"),
    ("gemini_3_1_pro",    "google/gemini-3.1-pro-preview"),
    ("deepseek_v4_pro",   "deepseek/deepseek-v4-pro"),
    ("deepseek_v4_flash", "deepseek/deepseek-v4-flash"),
    ("claude_sonnet_4_6", "anthropic/claude-sonnet-4.6"),
    ("glm_5_1",           "z-ai/glm-5.1"),
    ("kimi_k2_6",         "moonshotai/kimi-k2.6"),
]


def transform(src_text: str, model_dir: str, or_slug: str) -> str:
    out_lines: list[str] = []
    for line in src_text.splitlines(keepends=True):
        # Top-level name field
        if re.match(r"^name:\s*gpt5_full_pool\s*$", line.rstrip("\n")):
            out_lines.append(f"name: {model_dir}_full_pool\n")
            continue
        # Learner model name
        if re.match(r"^(\s*)model_name:\s*openai/gpt-5\s*$", line.rstrip("\n")):
            indent = re.match(r"^(\s*)", line).group(1)
            out_lines.append(f"{indent}model_name: openrouter/{or_slug}\n")
            continue
        # Drop the two local LLM proxy lines — LiteLLM handles routing + auth itself
        if re.match(r"^\s*api_base:\s*http://localhost:8000/v1\s*$", line.rstrip("\n")):
            continue
        if re.match(r"^\s*api_key:\s*dummy\s*$", line.rstrip("\n")):
            continue
        out_lines.append(line)
    text = "".join(out_lines)
    # If model_kwargs is now an empty mapping (both children dropped),
    # replace its body with `{}` to keep the YAML valid.
    text = re.sub(
        r"(^(?P<indent>\s*)model_kwargs:)\s*\n(?=\s*(?:[A-Za-z_][^:\n]*:|\Z|-\s|\#))",
        lambda m: f"{m.group('indent')}model_kwargs: {{}}\n",
        text,
        flags=re.MULTILINE,
    )
    return text


def main() -> None:
    DST_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for model_dir, or_slug in MODELS:
        out_subdir = DST_DIR / model_dir
        out_subdir.mkdir(parents=True, exist_ok=True)
        for game in GAMES:
            src = SRC_DIR / f"gpt5_{game}.yaml"  # configs/inverse/pool/gpt5/gpt5_<game>.yaml
            dst = out_subdir / f"{model_dir}_{game}.yaml"
            text = transform(src.read_text(), model_dir, or_slug)
            assert "openai/gpt-5" not in text, f"transform missed openai/gpt-5 in {src}"
            assert "gpt5_full_pool" not in text, f"transform missed top-level name in {src}"
            assert "localhost:8000" not in text, f"transform missed api_base in {src}"
            assert "api_key: dummy" not in text, f"transform missed api_key in {src}"
            assert f"openrouter/{or_slug}" in text, f"openrouter slug not inserted in {src}"
            assert f"name: {model_dir}_full_pool" in text, f"top-level name not inserted in {src}"
            dst.write_text(text)
            written += 1
            print(f"wrote {dst.relative_to(REPO_ROOT)}")
    print(f"\nDone: {written} configs written.")


if __name__ == "__main__":
    main()
