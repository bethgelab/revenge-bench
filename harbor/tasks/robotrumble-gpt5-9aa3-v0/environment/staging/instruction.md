You are a helpful assistant interacting continuously with a computer.
You'll be editing a codebase to recover another agent's strategy from game traces.

## Task Description

You are a programmer (learner) learning to recover another agent's RobotRumble strategy.

## Your Goal
Write code that produces the SAME actions as the target agent.
This is NOT about winning — it's about matching the target's behavior exactly.

## The Game: RobotRumble
RobotRumble is a turn-based robot battle game on a 19x19 grid.
- You control a team of robots (each is a "Soldier" unit with health points)
- Two teams: Blue and Red, each starting with multiple units
- Game lasts up to 100 turns
- Each turn, every unit executes your `robot(state, unit)` function independently

### Actions
Each unit can perform one action per turn:
- `{type: "Move", direction: "North"|"South"|"East"|"West"}` — move 1 cell
- `{type: "Attack", direction: "North"|"South"|"East"|"West"}` — attack adjacent cell

### State Object (passed to your function)
```javascript
state = {
  turn: 5,                    // current turn number (1-indexed)
  teams: {
    Blue: [                    // your team's units
      {id: "u1", coords: [3, 4], health: 5, team: "Blue", type: "Soldier"},
      ...
    ],
    Red: [                     // enemy team's units
      {id: "u2", coords: [7, 8], health: 3, team: "Red", type: "Soldier"},
      ...
    ]
  }
}
```

### Unit Object (passed to your function)
```javascript
unit = {
  id: "u1",
  coords: [3, 4],             // [x, y] position
  health: 5,                   // remaining health
  team: "Blue",
  type: "Soldier"
}
```

### Your Bot Function (robot.js)
```javascript
function robot(state, unit) {
    // state.turn - current turn number
    // state.objsByTeam(Team.Blue) - your team's units as Obj instances
    // state.objsByTeam(Team.Red) - enemy units as Obj instances
    // unit.coords - this unit's Coords {x, y}
    // unit.health - this unit's health

    // Return an Action:
    return Action.move(Direction.North)
    // or
    return Action.attack(Direction.East)
}
```

Your submission file is `robot.js`. Write a JavaScript function `robot(state, unit)`
that returns an Action. The stdlib provides Action, Direction, Coords, State, Obj, Team classes.

## How Evaluation Works (IMPORTANT)
- You do NOT play in the live game
- The target plays against an opponent to generate traces
- Your code is evaluated OFFLINE: for each state the target saw,
  we ask "what would your code do?" and compare to target's action
- Distance = mean action distance between your code and target (lower is better, 0 = perfect)
- Action distance: 0.0 if actions match exactly, 1.0 if they differ (type or direction)

## How It Works (IMPORTANT)
In this task session:
1. You PROBE first to test hypotheses about the target
2. You EDIT your submission based on probe results + traces
3. The verifier runs hidden target-vs-opponent simulations after you finish
4. You already have initial traces showing target's actions against different opponents
5. Your code is evaluated by action distance against target (lower = better, 0 = perfect)

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
  in any game situation, not just the specific turns you've seen.

## IMPORTANT: Probe-First Workflow

**Always probe BEFORE editing your submission.** Probes are your primary tool for
understanding the target. Traces only show what happened — probes let you
run controlled experiments.

**Recommended workflow for this session:**
1. Read `rounds/0/traces.json` — identify mismatches
2. Form a hypothesis (e.g., "target attacks when enemy is adjacent" or "target moves toward nearest enemy")
3. Design a probe to elicit specific behavior from the target (edit `probe.js` to create that scenario)
4. Run `sudo run_probe` and analyze `probe_trace_{N}.json`
5. Run 1-2 more probes to refine understanding
6. THEN edit your submission based on confirmed hypotheses

Probes are cheap and fast. Editing your submission without probing first is like
coding without testing — you'll waste rounds on wrong guesses.

## Inline Probing (YOUR PRIMARY TOOL)

You can run probe simulations AT ANY TIME during editing!

`probe.js` starts as a copy of `robot.js`.
You just need to modify it to create the test scenario you want, then run `sudo run_probe`.

### How to Probe
1. Edit `probe.js` implementing a strategy that will elicit the behavior you want to test
2. Run `sudo run_probe` — the system will play your probe against the target
3. Read `/workspace/probe_trace_{N}.json` to see what the target did in the situations your probe created

You have a bounded probe budget (see `/workspace/.probe_budget`; it decrements on each probe).

### CRITICAL: Separate Exploration from Exploitation

**`probe.js` is your EXPERIMENT. `robot.js` is your ANSWER. Keep them separate.**

Rules:
1. **`probe.js` must be DIFFERENT from `robot.js`.** If they're identical, the probe tells you nothing new.
2. **After each probe, STOP and analyze before probing again.** Write down:
   - What did you learn from the mismatch data?
   - What should you change in your submission based on this?
   - What should your next probe test?
   Never submit consecutive probes without analysis in between.
3. **Only edit your submission AFTER you have probe evidence.**

Think of it this way:
- **`probe.js` = laboratory** — run experiments here, it's safe to try wild things
- **`robot.js` = production** — only deploy validated findings here

### Probe Output Format
After each probe, results are written to a JSON file in your workspace:
`probe_trace_{N}.json`

```json
{
  "probe_id": 1,
  "description": "probe vs target - showing what each did in same state",
  "total_turns": 40,
  "num_simulations": 3,
  "pairs": [
    {
      "turn": 5,
      "probe_action": {"type": "Move", "direction": "North"},
      "target_action": {"type": "Attack", "direction": "East"},
      "distance": 1.0,
      "target_state": {...}
    }
  ]
}
```

Distance is 0.0 (identical action) or 1.0 (different action).

### Probe Strategy
- **Create specific scenarios**: Make probe always move one direction to see how target reacts
- **Test hypotheses**: "Does target attack adjacent enemies?" or "Does target retreat when low health?"
- **Explore edge cases**: See what target does with 1 unit vs many, surrounded vs open
- **Use probe_action vs target_action**: Direct comparison in same game state!
- **Look for invariants**: Target rules that hold across ALL opponents are the most reliable

## Key Files
- `robot.js` - Your recovered policy (EDIT THIS — evaluated by action distance). **Only edit after probing.**
- `probe.js` - Your experiment instrument (copy of `robot.js`). **Must differ from submission.** Starts as a submission copy.
- `docs/` - Game documentation and API reference
- `rounds/0/traces.json` - Initial normal-path-style distance summary and target-action mismatches for the starter bot
- `rounds/0/opp_*/sim_*.json` - Visible prior target-vs-opponent RobotRumble logs
- `/workspace/probe_trace_{N}.json` - Results from your probes

## Tips
- **PROBE FIRST** — don't jump straight to editing your submission
- **Keep `probe.js` different from `robot.js`** — identical probes waste your probe budget
- After each probe, write a brief analysis before probing again
- **Build opponent-invariant rules** — focus on what the target ALWAYS does
- Traces from different opponents reveal different aspects of the target's strategy
- `probe.js` is safe to experiment with — `robot.js` is your graded submission
- RobotRumble is multi-unit: your function is called once PER UNIT per turn
- Common patterns: attack adjacent enemies, move toward nearest enemy, retreat when low health, move to center

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
