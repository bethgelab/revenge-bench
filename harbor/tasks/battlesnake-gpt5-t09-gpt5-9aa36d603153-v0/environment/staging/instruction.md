You are a helpful assistant interacting continuously with a computer.
You'll be editing a codebase to recover another agent's strategy from game traces.

## Task Description

You are a programmer (learner) learning to recover another agent's BattleSnake strategy.

## Your Goal
Write code that produces the SAME actions as the target agent.
This is NOT about winning - it's about matching the target's behavior exactly.

## The Game: BattleSnake
BattleSnake is a multiplayer snake game on an 11x11 grid.
- Your snake moves every turn: "up", "down", "left", or "right"
- Eat food to grow longer and gain health
- Avoid walls, your own body, and other snakes
- If you collide or run out of health, you die

## How It Works (IMPORTANT)
You work in ONE container session (no rounds):
1. You PROBE the sealed target to test hypotheses about its behavior
2. You EDIT main.py based on what your probes reveal
3. When you finish, main.py is evaluated OFFLINE against fresh target-vs-opponent games generated after your work session — accuracy = how often your action matches the target's

## Prior Evidence + Probe Data

You start with a visible round-0 trace bundle generated from the normal
RevengeBench benchmark split: target vs the same sampled opponent pool used by
the normal path. These traces are prior evidence only — they are NOT the final
evaluation labels.

Each `sudo run_probe` plays several games between your probe bot and the target,
so a single probe yields many additional (state, action) pairs across diverse
board states.

**The target's strategy is FIXED and never changes.** Different probe bots and
different opponents create different board states, but they never change the
target's decision rules. Use this to your advantage:

- **Find invariant rules** — what does the target ALWAYS do, regardless of the
  situation? These are the core decision rules you need to code.
- **Cross-validate hypotheses** — if a rule holds in the prior traces but not
  in probes, it's probably not the right rule. True target rules are universal.
- **Don't overfit to visible traces or one probe** — build general rules that
  work in any game situation, not just the positions you happened to see.

## IMPORTANT: Probe-First Workflow

**Always probe BEFORE editing main.py.** Probes are your primary tool for
understanding the target. The visible round-0 traces show what happened in
the normal benchmark split; probes let you run controlled experiments against
the sealed target.

**Recommended workflow:**
1. Read `rounds/0/traces.json` — identify starter mismatches and current distance
2. Read the visible `rounds/0/opp_*/sim_*.jsonl` traces — identify target behavior across opponents
3. Form a hypothesis (e.g., "target prefers food over safety")
4. Design a probe to elicit specific behavior from the target (modify probe.py to create that scenario)
5. Run `sudo run_probe` and analyze `probe_trace_{N}.json`
6. Run 1-2 more probes to refine understanding
7. THEN edit main.py based on confirmed hypotheses

Probes are cheap and fast. Editing main.py without probing first is like
coding without testing — you'll waste your budget on wrong guesses.

## Inline Probing (YOUR PRIMARY TOOL)

You can run probe simulations AT ANY TIME during editing!

`probe.py` starts as a copy of `main.py`. You just need to modify it to
create the test scenario you want, then run `sudo run_probe`.

### How to Probe
1. Edit `probe.py` implementing a strategy that will elicit the behavior you want to test
2. Run `sudo run_probe` — the system will play your probe.py against the sealed target
3. Read `/workspace/probe_trace_{N}.json` to see what the target did in the situations your probe created

You have a bounded probe budget (see `/workspace/.probe_budget`; it
decrements on each probe and `probes_remaining` is reported in every result).
**Spend it deliberately — aim to use several probes before you settle on main.py.**

### ⚠️ CRITICAL: Separate Exploration from Exploitation

**`probe.py` is your EXPERIMENT. `main.py` is your SUBMISSION. Keep them separate.**

Rules:
1. **probe.py must be DIFFERENT from main.py.** If they're identical, the probe tells you nothing new — it just re-runs your current policy. Make probe.py test a specific hypothesis.
2. **After each probe, STOP and analyze before probing again.** Write down:
   - What did you learn from the mismatch data?
   - What should you change in main.py based on this?
   - What should your next probe test?
   Never submit consecutive probes without analysis in between.
3. **Only edit main.py AFTER you have probe evidence.** Each change to main.py should be justified by probe results showing the target behaves a certain way.

Think of it this way:
- **probe.py = laboratory** — run experiments here, it's safe to try wild things
- **main.py = production** — only deploy validated findings here

### Probe Output Format
Each probe writes `/workspace/probe_trace_{N}.json`:
```json
{
  "probe_id": 1,
  "description": "probe vs target - showing what each did in the same state",
  "total_turns": 45,
  "num_simulations": 3,
  "pairs": [
    {
      "turn": 5,
      "probe_action": "up",
      "target_action": "right",
      "distance": 1.0,
      "target_state": {...}
    }
  ],
  "probes_remaining": 9
}
```

### Probing Strategy
- **Create specific scenarios**: Make probe.py behave in ways that force interesting situations
- **Test hypotheses**: "Does target prefer food over safety?" - probe can help answer
- **Explore edge cases**: See what target does in corners, near walls, when chasing
- **Use probe_action vs target_action**: Direct comparison in same game state!
- **Look for invariants**: Target rules that hold across ALL opponents are the most reliable

## Key Files
- `main.py` - Your recovered policy (EDIT THIS - graded offline once at the end). **Only edit after probing.**
- `probe.py` - Your experiment instrument. **Must differ from main.py.** Starts as a copy of main.py.
- `docs/` - Game documentation and API reference
- `rounds/0/traces.json` - Initial normal-path-style distance summary and target-action mismatches for the starter bot
- `rounds/0/opp_*/sim_*.jsonl` - Visible prior target-vs-opponent traces generated with the normal benchmark split
- `/workspace/probe_trace_{N}.json` - Results from your probes (target's actions vs your probe's, per turn)
- `/workspace/.probe_budget` - How many probes you have left

## Tips
- **PROBE FIRST** — don't jump straight to editing main.py
- **Keep probe.py different from main.py** — identical probes waste your probe budget
- After each probe, write a brief analysis before probing again
- **Build opponent-invariant rules** — focus on what the target ALWAYS does
- Visible traces and probe games reveal different aspects of the target's strategy
- probe.py is safe to experiment with — main.py is your graded submission

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
 - `main.py`: Your code to edit (must match target's behavior)
 - `docs/`: Game documentation
 - `probe.py`: Your probe instrument — run `sudo run_probe` to query the sealed target
 - `probe_trace_*.json`: Saved probe results (your only window into the target)

## Visible Evidence + Probe Results

You work in a single container session — there is NO per-round scoring. You do
start with the same kind of round-0 feedback used by the normal benchmark:
`/workspace/rounds/0/traces.json` summarizes your starter `main.py`
against visible target-vs-opponent traces, and
`/workspace/rounds/0/opp_*/sim_*.jsonl` contains the raw traces. These are
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
      "learner_action": "up",
      "target_action": "down",
      "distance": 1.0,
      "state": {...}              // The exact game state - use this to debug!
    },
    ...
  ]
}
```

## Workflow

1. **Explore `/workspace`** - read `main.py`, `docs/`, and the game code
2. **Read `rounds/0/traces.json` first** - check starter distance and target-action mismatches
3. **Read visible raw traces** - inspect `rounds/0/opp_*/sim_*.jsonl` for target behavior across opponents
4. **Probe early** - edit `probe.py`, run `sudo run_probe`, then read the resulting `probe_trace_{N}.json`
5. **Look for patterns** - what rule is the target following across traces and probes?
6. **Update `main.py`** - implement the pattern you discovered
7. **Repeat while you have probe budget** - then leave `main.py` as your final policy; it is graded once, offline, after your session ends

This is a single continuous session (no rounds). Your conversation history —
earlier turns, tool outputs, and your own reasoning — stays visible throughout
(older outputs may be compacted to summaries to save context). There is no
repeated distance score during the session: the initial `traces.json`, visible
raw traces, and probes are your feedback, and `main.py` is graded once after
you finish against fresh hidden target traces.

IMPORTANT: Store all changes in /workspace or subdirectories.

## Tips

1. Re-read prior turns: your earlier analysis is still in this conversation.
2. Start by reading `rounds/0/traces.json` to see your starter distance and nonzero mismatches.
3. Use `rounds/0/opp_*/sim_*.jsonl` as prior evidence, not as final labels.
4. Probe before editing `main.py` — probes are your controlled experiments against the sealed target.
5. Each `probe_trace_{N}.json` shows, per turn, what your probe did and what the target did in the same state — focus on the turns where they differ.
6. The target likely follows simple rules (chase food, avoid walls, prefer certain directions).
7. Test a hypothesis by making `probe.py` force the situation, then re-probe.
8. You can write analysis scripts to process both `rounds/0` and `probe_trace_*.json`.
9. Keep everything inside `/workspace`.
