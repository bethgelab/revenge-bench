You are a helpful assistant interacting continuously with a computer.
You'll be editing a codebase to recover another agent's strategy from game traces.

## Task Description

You are a programmer (learner) learning to recover another agent's Halite strategy.

## Your Goal
Write code that produces the SAME actions as the target agent.
This is NOT about winning — it's about matching the target's behavior exactly.

## The Game: Halite
Halite is a multi-player turn-based strategy game on a rectangular grid.
- Players control pieces that move to capture territory and accumulate strength
- Each cell has production value that increases the strength of occupying pieces
- Pieces can move in 4 directions (north, east, south, west) or stay still
- Combat: when pieces from different players collide, strength determines the winner
- Goal: control the most territory by end of game

## Bot Implementation
Your bot is in the `submission/` folder. Supported languages: C, C++, OCaml, Rust.
Main file must be named `main.<ext>`. See `airesources/` for example implementations.
See `runGame.sh` under `submission/<language>/` for compile/run instructions.

## How It Works (IMPORTANT)
You work in ONE container session (no rounds):
1. You PROBE the sealed target to test hypotheses about its behavior
2. You EDIT your submission based on probe results + visible traces
3. When you finish, your submission is evaluated OFFLINE against fresh target-vs-opponent games generated after your work session — accuracy = how often your action matches the target's


## Multi-Opponent Advantage

Each round the target plays against MULTIPLE different opponents. This gives
you **richer data** — you see how the target behaves in diverse game situations
within a single task session.

**The target's strategy is FIXED and never changes.** Different opponents
create different board states, but the target's decision rules are constant.
Use this diversity to your advantage:

- **Find invariant rules** — what does the target ALWAYS do, regardless of
  which opponent it faces? These are the core decision rules you need to code.
- **Cross-validate hypotheses** — if a rule holds against opponent A but not
  opponent B, it's probably not the right rule. True target rules are universal.
- **Don't overfit to one opponent's traces** — build general rules that work
  in any game situation, not just the specific positions you've seen.

## IMPORTANT: Probe-First Workflow

**Always probe BEFORE editing your submission.** Probes are your primary tool for
understanding the target. Traces only show what happened — probes let you
run controlled experiments.

**Recommended workflow for this session:**
1. Read `rounds/0/traces.json` — identify mismatches
2. Form a hypothesis (e.g., "target prioritizes expansion over consolidation")
3. Design a probe to elicit specific behavior from the target (edit files in `probe/` to create that scenario)
4. Run `sudo run_probe` and analyze `probe_trace_{N}.json`
5. Run 1-2 more probes to refine understanding
6. THEN edit your submission based on confirmed hypotheses

Probes are cheap and fast. Editing your submission without probing first is like
coding without testing — you'll waste rounds on wrong guesses.

## Inline Probing (YOUR PRIMARY TOOL)

You can run probe simulations AT ANY TIME during editing!

`probe/` starts as a copy of `submission/`.
You just need to modify files in it to create the test scenario you want, then run `sudo run_probe`.

### How to Probe
1. Edit `probe/main.<ext>` implementing a strategy that will elicit the behavior you want to test
2. Run `sudo run_probe` — the system will play your probe against the target
3. Read `/workspace/probe_trace_{N}.json` to see what the target did in the situations your probe created

You have a bounded probe budget (see `/workspace/.probe_budget`; it decrements on each probe).

### CRITICAL: Separate Exploration from Exploitation

**`probe/` is your EXPERIMENT. `submission/` is your ANSWER. Keep them separate.**

Rules:
1. **`probe/` must be DIFFERENT from `submission/`.** If they're identical, the probe tells you nothing new.
2. **After each probe, STOP and analyze before probing again.** Write down:
   - What did you learn from the mismatch data?
   - What should you change in your submission based on this?
   - What should your next probe test?
   Never submit consecutive probes without analysis in between.
3. **Only edit your submission AFTER you have probe evidence.**

Think of it this way:
- **`probe/` = laboratory** — run experiments here, it's safe to try wild things
- **`submission/` = production** — only deploy validated findings here


### Probe Output Format
After each probe, results are written to a JSON file in your workspace:
`probe_trace_{N}.json`

```json
{
  "probe_id": 1,
  "description": "probe vs target - showing what each did in same state",
  "total_turns": 120,
  "num_simulations": 3,
  "pairs": [
    {
      "turn": 5,
      "probe_action": [[2, 3, 0], [4, 5, 1], [6, 7, 3]],
      "target_action": [[2, 3, 1], [4, 5, 1], [6, 7, 4]],
      "distance": 0.333,
      "target_state": {...}
    }
  ]
}
```

Actions are lists of `[row, col, move]` triples — one per owned cell.
Move values: 0=STILL, 1=NORTH, 2=EAST, 3=SOUTH, 4=WEST.
Distance is 0.0 (identical) to 1.0 (completely different).

### Probe Strategy
- **Create specific scenarios**: Make probe behave in ways that force interesting situations
- **Test hypotheses**: "Does target prioritize expansion or consolidation?"
- **Explore edge cases**: See what target does at borders, in combat, with low strength
- **Use probe_action vs target_action**: Direct comparison in same game state!
- **Look for invariants**: Target rules that hold across ALL opponents are the most reliable

## Key Files
- `submission/` - Your recovered policy (EDIT THIS — evaluated by action distance). **Only edit after probing.**
- `probe/` - Your experiment instrument (copy of `submission/`). **Must differ from submission.** Starts as a submission copy.
- `docs/` - Game documentation and API reference
- `rounds/0/traces.json` - Initial normal-path-style distance summary and target-action mismatches for the starter bot
- `rounds/0/opp_*/sim_*.hlt` - Visible prior target-vs-opponent Halite replays
- `/workspace/probe_trace_{N}.json` - Results from your probes


## Tips
- **PROBE FIRST** — don't jump straight to editing your submission
- **Keep `probe/` different from `submission/`** — identical probes waste your probe budget
- After each probe, write a brief analysis before probing again
- **Build opponent-invariant rules** — focus on what the target ALWAYS does
- Traces from different opponents reveal different aspects of the target's strategy
- `probe/` is safe to experiment with — `submission/` is your graded submission

## Strategy Recovery Guidelines

Your objective is to write code that produces the SAME actions as the target agent.
This is NOT about winning the game - it's about matching the target's behavior exactly.

**How evaluation works (IMPORTANT):**
- You do NOT play the game directly
- The target plays against an opponent, generating game traces
- Your code is evaluated OFFLINE: we call your code with each state the target saw
- Accuracy = how often your action matches what the target actually did
- Goal: If you were in the target's exact position, would you make the same decision?

The key files are in this codebase (/workspace):
 - `submission/`: Your recovered policy (must match target's behavior)
 - `probe/`: Your probe instrument — run `sudo run_probe` to query the sealed target
 - `rounds/0/traces.json`: Initial normal-path-style distance summary and target-action mismatches for the starter bot
 - `rounds/0/opp_*/sim_*.hlt`: Visible prior target-vs-opponent Halite replays
 - `probe_trace_*.json`: Saved probe results (your only window into the target)

## Visible Evidence + Probe Results

You work in a single container session — there is NO per-round scoring. You do
start with the same kind of round-0 feedback used by the normal benchmark:
`/workspace/rounds/0/traces.json` summarizes your starter `submission/`
against visible target-vs-opponent traces, and
`/workspace/rounds/0/opp_*/sim_*.hlt` contains the raw traces. These are
evidence, not final evaluation labels. Each `sudo run_probe` writes
`/workspace/probe_trace_{N}.json` with additional (state, action) pairs the
target produced against your probe.

### traces.json Format
```json
{
  "mean_distance": 0.75,         // Mean action distance (goal: 0.0 = perfect match)
  "total_actions": 100,           // Total states evaluated
  "total_distance": 75.0,         // Sum of action distances
  "nonzero_distances": [          // Actions with distance > 0 (with full state)
    {
      "turn": 5,
      "learner_action": [[2, 3, 0], [4, 5, 1]],
      "target_action": [[2, 3, 1], [4, 5, 1]],
      "distance": 1.0,
      "state": {...}              // The exact game state - use this to debug!
    },
    ...
  ]
}
```

## Workflow

1. **Explore `/workspace`** - read `submission/`, `probe/`
2. **Read `rounds/0/traces.json` first** - check starter distance and target-action mismatches
3. **Read visible raw traces** - inspect `rounds/0/opp_*/sim_*.hlt` for target behavior across opponents
4. **Probe early** - edit `probe/`, run `sudo run_probe`, then read the resulting `probe_trace_{N}.json`
5. **Look for patterns** - what rule is the target following across traces and probes?
6. **Update `submission/`** - implement the pattern you discovered
7. **Repeat while you have probe budget** - then leave `submission/` as your final policy; it is graded once, offline, after your session ends

This is a single continuous session (no rounds). Your conversation history —
earlier turns, tool outputs, and your own reasoning — stays visible throughout
(older outputs may be compacted to summaries to save context). There is no
repeated distance score during the session: the initial `traces.json`, visible
raw traces, and probes are your feedback, and `submission/` is graded once after
you finish against fresh hidden target traces.

IMPORTANT: Store all changes in /workspace or subdirectories.

## Tips

1. Re-read prior turns: your earlier analysis is still in this conversation.
2. Start by reading `rounds/0/traces.json` to see your starter distance and nonzero mismatches.
3. Use `rounds/0/opp_*/sim_*.hlt` as prior evidence, not as final labels.
4. Probe before editing `submission/` — probes are your controlled experiments against the sealed target.
5. Each `probe_trace_{N}.json` shows, per turn, what your probe did and what the target did in the same state — focus on the turns where they differ.
6. The target likely follows simple rules (chase food, avoid walls, prefer certain directions).
7. Test a hypothesis by making `probe/` force the situation, then re-probe.
8. You can write analysis scripts to process both `rounds/0` and `probe_trace_*.json`.
9. Keep everything inside `/workspace`.
