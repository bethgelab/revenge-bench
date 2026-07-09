You are a helpful assistant interacting continuously with a computer.
You'll be editing a codebase to recover another agent's strategy from game traces.

## Task Description

You are a programmer (learner) learning to recover another agent's RoboCode strategy.

## Your Goal
Write code that produces the SAME actions as the target agent.
This is NOT about winning — it's about matching the target's behavior exactly.

## The Game: RoboCode
RoboCode is a programming game on an 800×600 battlefield.
Your code controls a tank that must decide how to move, aim, and fire each turn.
The game is deterministic and turn-based.

### Actions (5-component output)
Each turn, your tank produces 5 values:
- `velocity`: speed [-8, 8] px/turn
- `turn_body`: body rotation [-10, 10] degrees/turn (total heading delta)
- `turn_gun`: gun rotation [-20, 20] degrees/turn (total heading delta)
- `turn_radar`: radar rotation [-45, 45] degrees/turn (total heading delta)
- `fire_power`: bullet power [0, 3] (0 = don't fire)

**IMPORTANT**: `turn_gun` and `turn_radar` are TOTAL heading deltas, not independent.
The gun sits on the body —  when the body turns, the gun turns with it.
Similarly, the radar sits on the gun. The recorded deltas already include this coupling.

### Game State (what your move() function receives)
Each game turn provides these values:
```
tick            - current game tick
my_x            - your x position
my_y            - your y position
my_heading      - body angle (degrees, clockwise from North)
my_gun_heading  - gun angle (degrees, clockwise from North)
my_radar_heading - radar angle (degrees, clockwise from North)
my_energy       - remaining energy
my_velocity     - current speed
my_gun_heat     - gun cooldown (can fire when 0.0)
enemy_x         - enemy x position
enemy_y         - enemy y position
enemy_heading   - enemy body angle (degrees)
enemy_energy    - enemy energy
enemy_velocity  - enemy speed
enemy_distance  - distance to enemy
enemy_bearing   - bearing to enemy (degrees, relative to your heading)
arena_width     - battlefield width (800)
arena_height    - battlefield height (600)
```

### Critical Geometric Relationships
RoboCode uses a **clockwise-from-North** coordinate system. These formulas are essential:

```python
import math

# Absolute bearing to enemy (degrees, clockwise from North)
abs_bearing = math.degrees(math.atan2(
    state["enemy_x"] - state["my_x"],
    state["enemy_y"] - state["my_y"]
)) % 360

# Gun offset: how far the gun must turn to point at enemy
gun_offset = normalize_angle(abs_bearing - state["my_gun_heading"])
# → Use this for turn_gun, NOT enemy_bearing!

# Radar offset: how far the radar must turn to point at enemy
radar_offset = normalize_angle(abs_bearing - state["my_radar_heading"])
# → Common pattern: turn_radar = clamp(2 * radar_offset, -45, 45) for radar lock

# Body offset: how far body must turn to face enemy
# → This equals enemy_bearing (already provided in state)
```

**Common mistake**: Using `enemy_bearing` for gun/radar aiming. The gun and radar
have their own headings (my_gun_heading, my_radar_heading) independent of the body.
You MUST compute gun_offset and radar_offset from absolute bearing.

### Your Submission: `main.py`
Write a Python `move(state)` function that receives a game state dict and
returns a 5-component action dict matching the target's behavior.

A starter `main.py` is already provided with correct geometric computations.
Modify it to match the target's specific strategy.

## How Evaluation Works (IMPORTANT)
- You do NOT play in the live game during evaluation
- The target plays against opponents to generate traces (XML recordings)
- For each turn, we extract the target's state and action from the recording
- Your `move(state)` function is called with the exact state the target saw
- Your returned action dict is compared to the target's actual action
- Distance = average normalized difference across all 5 components (0 = perfect match)
- **All your decision logic goes in `move()`** — that is what gets evaluated

### Per-Component Scoring
Each component is scored independently:
- velocity: |diff| / 16  (range is [-8, 8])
- turn_body: |diff| / 20  (range is [-10, 10])
- turn_gun: |diff| / 40  (range is [-20, 20])
- turn_radar: |diff| / 90  (range is [-45, 45])
- fire_power: |diff| / 3  (range is [0, 3])
The overall distance is the mean of these 5 normalized errors.
Check `traces.json` for per-component breakdowns to see which components need work.

## How It Works (IMPORTANT)
Each round:
1. You PROBE first to test hypotheses about the target
2. You EDIT your submission based on probe results + traces
3. At round end, main simulation runs: target vs MULTIPLE opponents
4. You get traces showing target's actions against different opponents
5. Your code is evaluated by action distance against target (lower = better, 0.0 = perfect)

## Multi-Opponent Advantage

Each round the target plays against MULTIPLE different opponents. This gives
you **richer data** — you see how the target behaves in diverse game situations
within a single round.

**The target's strategy is FIXED and never changes.** Different opponents
create different battlefield conditions, but the target's decision rules are constant.
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

**Recommended workflow each round:**
1. Read `rounds/0/traces.json` — identify mismatches (check `component_errors` for worst components)
2. Form a hypothesis (e.g., "target aims gun at enemy" or "target fires only when close")
3. Design a probe to elicit specific behavior from the target (edit Java files in `probe/` to create that scenario)
4. Run `sudo run_probe` and analyze `probe_trace_{N}.json`
5. Run 1-2 more probes to refine understanding
6. THEN edit `main.py` based on confirmed hypotheses

Probes are cheap and fast. Editing your submission without probing first is like
coding without testing — you'll waste rounds on wrong guesses.

## Inline Probing (YOUR PRIMARY TOOL)

You can run probe simulations AT ANY TIME during editing!

`probe/` starts as a copy of `robots/custom/`.
You modify the Java bot in `probe/` to create specific game situations, then run `sudo run_probe`.

### How to Probe
1. Edit Java files in `probe/` implementing a bot that will elicit the behavior you want to test
2. Run `sudo run_probe` — the system will play your probe bot against the target
3. Read the results to see how the target responded in the situations your probe created

You have a bounded total probe budget for this single session. The remaining budget is tracked in `/workspace/.probe_budget`, and each successful `sudo run_probe` decrements it. **Spend it deliberately — aim to use several probes before finalizing main.py.**

### CRITICAL: Separate Exploration from Exploitation

**`probe/` is your EXPERIMENT. `main.py` is your ANSWER. Keep them separate.**

Rules:
1. **`probe/` must create DIFFERENT situations from normal play.** If the probe just plays normally, it tells you nothing new.
2. **After each probe, STOP and analyze before probing again.** Write down:
   - What did you learn from the target's behavior?
   - What should you change in your submission based on this?
   - What should your next probe test?
   Never submit consecutive probes without analysis in between.
3. **Only edit your submission AFTER you have probe evidence.**

Think of it this way:
- **`probe/` = laboratory** — create game situations here, it's safe to try wild things
- **`main.py` = production** — only deploy validated findings here

### Probe Output Format
After each probe, results are written to a JSON file in your workspace:
`probe_trace_{probe_num}.json`

```json
{
  "probe_id": 1,
  "description": "probe (p0) vs target (p1) — action comparison per tick",
  "total_turns": 100,
  "num_simulations": 3,
  "pairs": [
    {
      "turn": 5,
      "probe_action": {"velocity": 8, "turn_body": 5, "turn_gun": -3, "turn_radar": 10, "fire_power": 2},
      "target_action": {"velocity": 6, "turn_body": -2, "turn_gun": 8, "turn_radar": -15, "fire_power": 1},
      "distance": 0.15,
      "target_state": {...}
    }
  ]
}
```

Actions are 5-component dicts. Distance is 0.0 (identical) to 1.0 (completely different).

### Probe Strategy
- **Create specific scenarios**: Make a probe bot that charges, retreats, or circles to see how the target reacts
- **Test hypotheses**: "Does target fire more at close range?" or "Does target track with radar oscillation?"
- **Explore edge cases**: See what target does against a stationary bot, a fast-moving bot, or when energy is low
- **Use probe_action vs target_action**: Direct comparison per tick in the same game!
- **Look for invariants**: Target rules that hold across ALL situations are the most reliable

## Key Files
- `main.py` - **YOUR SUBMISSION** — Python file with `move(state)` function. **Only edit after probing.**
- `probe/` - Your experiment instrument (Java bot). **Must create different scenarios.** Auto-seeded each round.
- `docs/` - Game documentation and API reference
- `rounds/0/traces.json` - Initial normal-path-style distance summary and per-component error breakdowns for the starter bot
- `rounds/0/opp_*/record_*.xml` - Visible prior target-vs-opponent XML traces
- `probe_trace_{N}.json` - Results from `sudo run_probe` calls

## Tips for Strategy Recovery
1. **PROBE FIRST** — don't jump straight to editing your submission
2. **Write analysis scripts** — don't eyeball traces. Write Python to compute
   correlations, histograms, and regressions on the nonzero_distances entries.
3. **Focus on the worst component first** — check `component_errors` in traces.json
   to see which of the 5 components contributes most error.
4. **Use geometry for aiming** — compute `abs_bearing`, `gun_offset`, `radar_offset`
   from (my_x, my_y, enemy_x, enemy_y) and the heading fields.
5. **Radar lock pattern**: Many bots use `turn_radar = clamp(2 * radar_offset, -45, 45)`
   to oscillate the radar around the enemy.
6. **Gun aiming**: Most bots aim the gun directly at enemy: `turn_gun = clamp(gun_offset, -20, 20)`.
7. **Movement is state-dependent** — velocity often depends on distance, energy, or timing.
   Don't hardcode tick-specific sequences — they won't generalize across opponents.
8. **Fire power tiers** — check if firing depends on distance, energy, or gun_heat.
9. **Build opponent-invariant rules** — focus on what the target ALWAYS does.
10. `probe/` is safe to experiment with — `main.py` is your graded submission.

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
 - `main.py`: Your Python policy to edit (must match target's behavior)
 - `probe/`: Your Java probe bot — run `sudo run_probe` to query the sealed target
 - `rounds/0/traces.json`: Initial normal-path-style distance summary and target-action mismatches for the starter bot
 - `rounds/0/opp_*/record_*.xml`: Visible prior target-vs-opponent RoboCode XML recordings
 - `probe_trace_*.json`: Saved probe results (your only window into the target)

## Visible Evidence + Probe Results

You work in a single container session — there is NO per-round scoring. You do
start with the same kind of round-0 feedback used by the normal benchmark:
`/workspace/rounds/0/traces.json` summarizes your starter `main.py`
against visible target-vs-opponent traces, and
`/workspace/rounds/0/opp_*/record_*.xml` contains the raw traces. These are
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
      "learner_action": {"velocity": 8, "turn_body": 5, "turn_gun": -3, "turn_radar": 10, "fire_power": 2},
      "target_action": {"velocity": 6, "turn_body": -2, "turn_gun": 8, "turn_radar": -15, "fire_power": 1},
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
3. **Read visible raw traces** - inspect `rounds/0/opp_*/record_*.xml` for target behavior across opponents
4. **Probe early** - edit `probe/`, run `sudo run_probe`, then read the resulting `probe_trace_{N}.json`
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
3. Use `rounds/0/opp_*/record_*.xml` as prior evidence, not as final labels.
4. Probe before editing `main.py` — probes are your controlled experiments against the sealed target.
5. Each `probe_trace_{N}.json` shows, per turn, what your probe did and what the target did in the same state — focus on the turns where they differ.
6. The target likely follows simple rules (chase food, avoid walls, prefer certain directions).
7. Test a hypothesis by making `probe/` force the situation, then re-probe.
8. You can write analysis scripts to process both `rounds/0` and `probe_trace_*.json`.
9. Keep everything inside `/workspace`.
