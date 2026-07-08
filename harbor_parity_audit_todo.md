# Harbor Parity Audit TODO

Temporary checklist from the Harbor-vs-normal-path audit. Remove this file once
the items are fixed and covered by tests.

## Findings To Fix

- [x] High: player-order drift in generated Harbor traces.
  - Normal path calls `random.shuffle(agents)` before each round/opponent in
    `src/revenge_bench/arenas/arena.py`.
  - BattleSnake normal path also shuffles CLI player order per simulation in
    `src/revenge_bench/arenas/battlesnake/battlesnake.py`.
  - Harbor BattleSnake currently always passes target first and opponent second.
  - Harbor RoboCode currently always maps target to `p0` and opponent to `p1`.
  - Harbor Halite and RobotRumble currently use deterministic
    `random.Random(seed + opp_idx).shuffle(...)`, not the normal path's runtime
    process shuffle.

- [x] Medium: Halite Harbor validation is looser than normal path.
  - Normal path requires exactly one supported `main.*`, with special Rust
    `src/main.rs` handling.
  - Harbor `compile_submission()` silently picks the first supported `main.*`.

- [x] Medium: BattleSnake trace generation suppresses engine failures.
  - Harbor BattleSnake uses `check=False`, suppresses stdout/stderr, and does
    not verify each `sim_*.jsonl` exists/nonempty.
  - The normal path is also forgiving, but the Harbor parity contract says
    trace generators should fail on missing/empty labels.

- [x] Coverage gap: current parity tests prove scoring parity, not trace
  generation parity.
  - Add tests that guard player-order behavior and Halite validation parity.

## Completion Checks

- [x] Harbor tests pass.
- [x] Relevant trace/offline-eval tests pass.
- [x] Checklist items above are marked complete or this file is removed.
