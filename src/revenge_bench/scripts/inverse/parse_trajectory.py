"""Token-usage analysis utilities for mini-SWE-agent trajectory files.

Parses the per-call API responses stored in ``.traj.json`` files and produces
a breakdown of prompt/completion token consumption by action category.

Categories
----------
setup       – first API call (system prompt + initial task description)
file_read   – agent ran cat/grep/head/tail/diff on a file
file_edit   – agent wrote to a file (echo >, tee, sed -i, …)
navigation  – agent listed/found/explored the filesystem
probe       – agent submitted a probe (PROBE_SUBMIT)
other       – anything else (compilation, execution, etc.)
"""

import json
import re
from pathlib import Path

# Patterns for action classification (order matters — more specific first)
_FILE_EDIT_PATTERN = re.compile(
    r'(>(?!=)|>>|\btee\b|\bprintf\b.*>|\bcat\s*<<|\bsed\s+-i|\bawk\b.*>|\bcp\b|\bmv\b|\bwrite\b|\btruncate\b)',
    re.IGNORECASE,
)
_FILE_READ_PATTERN = re.compile(
    r'\b(cat|less|head|tail|grep|awk|sed(?!\s+-i)|diff|wdiff)\b',
    re.IGNORECASE,
)
_NAVIGATION_PATTERN = re.compile(
    r'\b(ls|find|pwd|wc|stat|du|file|echo|tree|locate)\b',
    re.IGNORECASE,
)
_BASH_BLOCK_PATTERN = re.compile(r'```(?:bash|sh|shell)?\s*\n(.*?)```', re.DOTALL)

ALL_CATEGORIES = ("setup", "file_read", "file_edit", "navigation", "probe", "other")


def classify_action(action: str) -> str:
    """Classify a bash action into a token usage category."""
    action = action.strip()
    if not action:
        return "other"
    if "PROBE_SUBMIT" in action:
        return "probe"
    # Edit before read: `cat file | tee output` counts as an edit
    if _FILE_EDIT_PATTERN.search(action):
        return "file_edit"
    if _FILE_READ_PATTERN.search(action):
        return "file_read"
    if _NAVIGATION_PATTERN.search(action):
        return "navigation"
    return "other"


def extract_bash_action(content: str) -> str:
    """Extract the first bash command block from an assistant message."""
    match = _BASH_BLOCK_PATTERN.search(content)
    if match:
        return match.group(1).strip()
    # Fallback: bare command line (no fences)
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("THOUGHT", "ACTION", "#", "```")):
            return stripped
    return ""


def analyze_traj(traj_path: Path) -> dict:
    """Parse a trajectory file and return detailed per-call and aggregated token usage.

    Each assistant message stores the full API response (OpenRouter / Anthropic / OpenAI)
    including a ``usage`` dict.  We walk the message list to compute incremental context
    growth at every step and attribute it to the action that caused it.

    Returns a dict with keys ``totals``, ``by_category``, and ``per_call``.
    Returns an empty dict on any parse error.
    """
    try:
        traj = json.loads(traj_path.read_text())
    except Exception:
        return {}

    messages = traj.get("messages", [])
    per_call: list[dict] = []
    prev_prompt_tokens = 0
    prev_action = ""
    prev_action_category = "setup"  # first call is always "setup"

    for msg in messages:
        if msg.get("role") != "assistant":
            continue

        content = msg.get("content") or ""
        usage = msg.get("extra", {}).get("response", {}).get("usage", {})
        if not usage:
            continue

        prompt_tokens: int = usage.get("prompt_tokens", 0)
        completion_tokens: int = usage.get("completion_tokens", 0)
        cost: float = usage.get("cost", 0.0)
        cached_tokens: int = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0) or 0
        cache_write_tokens: int = usage.get("prompt_tokens_details", {}).get("cache_write_tokens", 0) or 0
        reasoning_tokens: int = (
            usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0) or 0
        )

        incremental_prompt = prompt_tokens - prev_prompt_tokens

        per_call.append({
            "call_index": len(per_call),
            # What the agent did BEFORE this call (whose output grew the context)
            "action": prev_action,
            "action_category": prev_action_category,
            "prompt_tokens": prompt_tokens,
            "incremental_prompt_tokens": incremental_prompt,
            "completion_tokens": completion_tokens,
            "reasoning_tokens": reasoning_tokens,
            "cached_tokens": cached_tokens,
            "cache_write_tokens": cache_write_tokens,
            "cost": cost,
        })

        current_action = extract_bash_action(content)
        prev_prompt_tokens = prompt_tokens
        prev_action = current_action
        prev_action_category = classify_action(current_action) if current_action else "other"

    # Aggregate by category
    by_category: dict[str, dict] = {}
    for call in per_call:
        cat = call["action_category"]
        entry = by_category.setdefault(cat, {
            "incremental_prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "api_calls": 0,
            "cost": 0.0,
        })
        entry["incremental_prompt_tokens"] += call["incremental_prompt_tokens"]
        entry["completion_tokens"] += call["completion_tokens"]
        entry["reasoning_tokens"] += call["reasoning_tokens"]
        entry["api_calls"] += 1
        entry["cost"] += call["cost"]

    totals: dict = {}
    if per_call:
        last = per_call[-1]
        totals = {
            "total_prompt_tokens": last["prompt_tokens"],
            "total_completion_tokens": sum(c["completion_tokens"] for c in per_call),
            "total_reasoning_tokens": sum(c["reasoning_tokens"] for c in per_call),
            # Sum cached_tokens across all calls (true cumulative hit rate).
            # Using only the last call would overstate caching by ignoring the
            # cold-start period where early calls have zero cache hits.
            "total_cached_tokens": sum(c["cached_tokens"] for c in per_call),
            "total_prompt_tokens_all_calls": sum(c["prompt_tokens"] for c in per_call),
            "api_calls": len(per_call),
            "total_cost": sum(c["cost"] for c in per_call),
        }

    return {"totals": totals, "by_category": by_category, "per_call": per_call}


def empty_totals() -> dict:
    return {
        "total_prompt_tokens": 0,
        "total_prompt_tokens_all_calls": 0,
        "total_completion_tokens": 0,
        "total_reasoning_tokens": 0,
        "total_cached_tokens": 0,
        "api_calls": 0,
        "total_cost": 0.0,
        "traj_count": 0,
    }


def empty_by_category() -> dict:
    return {
        cat: {"incremental_prompt_tokens": 0, "completion_tokens": 0,
              "reasoning_tokens": 0, "api_calls": 0, "cost": 0.0}
        for cat in ALL_CATEGORIES
    }


def accumulate(totals: dict, by_category: dict, result: dict) -> None:
    """Add a single traj analysis result into running totals (in-place)."""
    t = result.get("totals", {})
    totals["total_prompt_tokens"] += t.get("total_prompt_tokens", 0)
    totals["total_prompt_tokens_all_calls"] += t.get("total_prompt_tokens_all_calls", 0)
    totals["total_completion_tokens"] += t.get("total_completion_tokens", 0)
    totals["total_reasoning_tokens"] += t.get("total_reasoning_tokens", 0)
    totals["total_cached_tokens"] += t.get("total_cached_tokens", 0)
    totals["api_calls"] += t.get("api_calls", 0)
    totals["total_cost"] += t.get("total_cost", 0.0)
    totals["traj_count"] = totals.get("traj_count", 0) + 1

    for cat, stats in result.get("by_category", {}).items():
        entry = by_category[cat]
        entry["incremental_prompt_tokens"] += stats["incremental_prompt_tokens"]
        entry["completion_tokens"] += stats["completion_tokens"]
        entry["reasoning_tokens"] += stats["reasoning_tokens"]
        entry["api_calls"] += stats["api_calls"]
        entry["cost"] += stats["cost"]
