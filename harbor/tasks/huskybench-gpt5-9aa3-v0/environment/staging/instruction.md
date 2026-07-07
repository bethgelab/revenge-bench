You are a helpful assistant interacting continuously with a computer.
You'll be editing a codebase to recover another agent's strategy from game traces.

## Task Description

You are a programmer (learner) learning to recover another agent's poker strategy.

## Your Goal
Write code that produces the SAME actions as the target agent.
This is NOT about winning — it's about matching the target's behavior exactly.

## The Game: HuskyBench (Poker)
HuskyBench is a heads-up No-Limit Texas Hold'em poker game.
- Each hand: you get 2 hole cards, then community cards are revealed over 4 rounds
- Betting rounds: preflop, flop (3 cards), turn (4 cards), river (5 cards)
- Actions: FOLD, CHECK, CALL, or RAISE:<ratio>
- Raise ratio: amount / player_stack, a float in (0, 1] (1.0 = all-in)
- Starting stack: 10,000 chips

## How Evaluation Works (IMPORTANT)
- You do NOT play in the live game
- The target plays against an opponent to generate traces
- Your code is evaluated OFFLINE: for each decision point the target faced,
  we ask "what would your code do?" and compare to target's action
- Distance = mean action distance between your code and target (lower is better, 0 = perfect)
- Action distance uses a log-commitment scale normalized per the actor's
  stack S at the decision point: FOLD is distance 1.0 from every non-FOLD
  action, CHECK/CALL are passive (treated as RAISE:0), and two raises with
  ratios r1 and r2 are compared by |c(r1; S) - c(r2; S)| where
  c(r; S) = log1p(r * S) / log1p(S). Under this scale small raises are
  meaningfully separated from CHECK/CALL, and an all-in is always
  distance 1 from CHECK — regardless of how short the stack is. Matching
  the target's raise magnitude is worth more than matching its ratio to
  within a few percent.

## Your Bot Class (client/player.py)
Your submission file is `client/player.py`. It must define a class that subclasses `Bot`
and implements ALL required methods. The starter code already has the right structure.

**IMPORTANT: You MUST implement all 5 methods below.** If any are missing, your bot
will fail to instantiate and evaluation will fail. Do NOT remove any methods when editing.

```python
from typing import List, Tuple
from bot import Bot
from type.poker_action import PokerAction
from type.round_state import RoundStateClient

class SimplePlayer(Bot):
    def __init__(self):
        super().__init__()

    def on_start(self, starting_chips: int, player_hands: List[str], blind_amount: int,
                 big_blind_player_id: int, small_blind_player_id: int, all_players: List[int]):
        """Called once at game start. Store your hole cards here."""
        self.my_hand = player_hands
        self.blind_amount = blind_amount

    def on_round_start(self, round_state: RoundStateClient, remaining_chips: int):
        """Called at the start of each betting round."""
        pass

    def get_action(self, round_state: RoundStateClient, remaining_chips: int) -> Tuple[PokerAction, int]:
        # round_state fields:
        #   round_state.round       - "preflop", "flop", "turn", "river"
        #   round_state.community_cards - list of visible community cards
        #   round_state.pot         - current pot size
        #   round_state.current_bet - amount to call
        #   round_state.min_raise   - minimum raise amount
        #   round_state.max_raise   - maximum raise amount
        #   round_state.player_bets - dict of player bets
        #   round_state.player_actions - dict of player actions
        #   round_state.player_money - dict of player chip counts
        #   round_state.round_num   - hand number
        #
        # self.my_hand  - your 2 hole cards (set in on_start above)
        #
        # Return (PokerAction, amount):
        #   (PokerAction.FOLD, 0)
        #   (PokerAction.CHECK, 0)
        #   (PokerAction.CALL, 0)
        #   (PokerAction.RAISE, amount)  - amount in chips (converted to ratio internally)
        #   (PokerAction.ALL_IN, 0)

        if round_state.current_bet == 0:
            return PokerAction.CHECK, 0
        return PokerAction.CALL, 0

    def on_end_round(self, round_state: RoundStateClient, remaining_chips: int):
        """Called at the end of every round."""
        pass

    def on_end_game(self, round_state: RoundStateClient, player_score: float,
                    all_scores: dict, active_players_hands: dict):
        """Called once when the game finishes."""
        pass
```

Action distance for evaluation (log-commitment scale, per-state normalized):
FOLD is distance 1.0 from any non-FOLD action; CHECK/CALL are passive
(treated as RAISE:0); raises are compared via c(r; S) = log1p(r * S) / log1p(S)
where S is the actor's stack at the decision. An all-in is always
distance 1 from CHECK, at any stack size.

## How It Works (IMPORTANT)

This Harbor task is one continuous session:
1. You start with visible round-0 target-vs-opponent traces and the starter's `traces.json`
2. You can run controlled probes with `sudo run_probe`
3. You edit `client/player.py` based on visible traces + probe results
4. Your final `client/player.py` is evaluated once offline against fresh hidden target traces
5. Your code is scored by action distance against target (lower = better, 0 = perfect)


## Multi-Opponent Advantage

The visible round-0 data shows MULTIPLE different opponents. This gives
you **richer data** — you see how the target behaves in diverse game situations
within the initial evidence set.

**The target's strategy is FIXED and never changes.** Different opponents
create different hand histories, but the target's decision rules are constant.
Use this diversity to your advantage:

- **Find invariant rules** — what does the target ALWAYS do, regardless of
  which opponent it faces? These are the core decision rules you need to code.
- **Cross-validate hypotheses** — if a rule holds against opponent A but not
  opponent B, it's probably not the right rule. True target rules are universal.
- **Don't overfit to one opponent's traces** — build general rules that work
  in any game situation, not just the specific hands you've seen.

## IMPORTANT: Probe-First Workflow

**Always probe BEFORE editing your submission.** Probes are your primary tool for
understanding the target. Traces only show what happened — probes let you
run controlled experiments.

**Recommended workflow:**
1. Read traces.json — identify mismatches
2. Form a hypothesis (e.g., "target folds weak hands preflop" or "target always raises with pocket pairs")
3. Design a probe to elicit specific behavior from the target (edit files in `probe/` to create that scenario)
4. Run `sudo run_probe` and analyze results
5. Run 1-2 more probes to refine understanding
6. THEN edit your submission based on confirmed hypotheses

Probes are cheap and fast. Editing your submission without probing first is like
coding without testing — you'll waste your limited probe budget.

## Inline Probing (YOUR PRIMARY TOOL)

You can run probe simulations AT ANY TIME during editing!

`probe/client/player.py` starts as a copy of the starter `client/player.py` in this single session.
You modify it to create the test scenario you want, then run `sudo run_probe`.

### How to Probe
1. Edit `probe/client/player.py` implementing a strategy that will elicit the behavior you want to test
2. Run `sudo run_probe` — the system will play your probe against the target
3. Read the results to see what the target did in the situations your probe created

You get a limited total probe budget for the session. **Aim to use probes deliberately and analyze each result.**

### CRITICAL: Separate Exploration from Exploitation

**`probe/` is your EXPERIMENT. `client/player.py` is your ANSWER. Keep them separate.**

Rules:
1. **`probe/client/player.py` must be DIFFERENT from `client/player.py`.** If they're identical, the probe tells you nothing new.
2. **After each probe, STOP and analyze before probing again.** Write down:
   - What did you learn from the mismatch data?
   - What should you change in your submission based on this?
   - What should your next probe test?
   Never submit consecutive probes without analysis in between.
3. **Only edit your submission AFTER you have probe evidence.**

Think of it this way:
- **`probe/` = laboratory** — run experiments here, it's safe to try wild things
- **`client/player.py` = production** — only deploy validated findings here

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
      "probe_action": "RAISE:0.5000",
      "target_action": "CALL",
      "distance": 0.5,
      "target_state": {...}
    }
  ]
}
```

Actions are normalized: FOLD, CHECK, CALL, or RAISE:<ratio>.
Distance is 0.0 (identical) to 1.0 (completely different).

### Probe Strategy
- **Create specific scenarios**: Make probe bet aggressively/passively to see how target responds
- **Test hypotheses**: "Does target fold to large raises?" or "Does target bluff on the river?"
- **Explore edge cases**: See what target does with small stacks, big pots, different board textures
- **Use probe_action vs target_action**: Direct comparison in same game state!
- **Look for invariants**: Target rules that hold across ALL opponents are the most reliable

## Key Files
- `client/player.py` - Your recovered policy (EDIT THIS — evaluated by action distance). **Only edit after probing.**
- `probe/client/player.py` - Your experiment instrument (copy of `client/player.py`). **Must differ from submission.**
- `docs/` - Game documentation and API reference
- `rounds/0/traces.json` - Starter distance results and nonzero_distances
- `rounds/0/opp_*/game_log_*.json` - Visible raw game logs (target vs MULTIPLE opponents)
- `probe_trace_*.json` - Probe results from `sudo run_probe`

## Tips
- **PROBE FIRST** — don't jump straight to editing your submission
- **Keep `probe/` different from `client/player.py`** — identical probes waste your probe budget
- After each probe, write a brief analysis before probing again
- **Build opponent-invariant rules** — focus on what the target ALWAYS does
- Traces from different opponents reveal different aspects of the target's strategy
- `probe/` is safe to experiment with — `client/player.py` is your graded submission
- Card notation: rank + suit (Ah=Ace of hearts, Td=10 of diamonds, 2c=2 of clubs)

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
 - `client/player.py`: Your recovered poker bot policy (must match target's behavior)
 - `probe/client/player.py`: Your probe poker bot — run `sudo run_probe` to query the sealed target
 - `rounds/0/traces.json`: Initial normal-path-style distance summary and target-action mismatches for the starter bot
 - `rounds/0/opp_*/game_log_*.json`: Visible prior target-vs-opponent HuskyBench poker hand logs
 - `probe_trace_*.json`: Saved probe results (your only window into the target)

## Visible Evidence + Probe Results

You work in a single container session — there is NO per-round scoring. You do
start with the same kind of round-0 feedback used by the normal benchmark:
`/workspace/rounds/0/traces.json` summarizes your starter `client/player.py`
against visible target-vs-opponent traces, and
`/workspace/rounds/0/opp_*/game_log_*.json` contains the raw traces. These are
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
      "learner_action": "CALL",
      "target_action": "RAISE:0.2500",
      "distance": 1.0,
      "state": {...}              // The exact game state - use this to debug!
    },
    ...
  ]
}
```

## Workflow

1. **Explore `/workspace`** - read `client/player.py`, `probe/client/player.py`, and the game code
2. **Read `rounds/0/traces.json` first** - check starter distance and target-action mismatches
3. **Read visible raw traces** - inspect `rounds/0/opp_*/game_log_*.json` for target behavior across opponents
4. **Probe early** - edit `probe/client/player.py`, run `sudo run_probe`, then read the resulting `probe_trace_{N}.json`
5. **Look for patterns** - what rule is the target following across traces and probes?
6. **Update `client/player.py`** - implement the pattern you discovered
7. **Repeat while you have probe budget** - then leave `client/player.py` as your final policy; it is graded once, offline, after your session ends

This is a single continuous session (no rounds). Your conversation history —
earlier turns, tool outputs, and your own reasoning — stays visible throughout
(older outputs may be compacted to summaries to save context). There is no
repeated distance score during the session: the initial `traces.json`, visible
raw traces, and probes are your feedback, and `client/player.py` is graded once after
you finish against fresh hidden target traces.

IMPORTANT: Store all changes in /workspace or subdirectories.

## Tips

1. Re-read prior turns: your earlier analysis is still in this conversation.
2. Start by reading `rounds/0/traces.json` to see your starter distance and nonzero mismatches.
3. Use `rounds/0/opp_*/game_log_*.json` as prior evidence, not as final labels.
4. Probe before editing `client/player.py` — probes are your controlled experiments against the sealed target.
5. Each `probe_trace_{N}.json` shows, per turn, what your probe did and what the target did in the same state — focus on the turns where they differ.
6. The target likely follows poker rules based on hole cards, board texture, betting round, current bet, pot odds, stack, and action history.
7. Test a hypothesis by making `probe/client/player.py` force the situation, then re-probe.
8. You can write analysis scripts to process both `rounds/0` and `probe_trace_*.json`.
9. Keep everything inside `/workspace`.
