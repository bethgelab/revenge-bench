# Harbor Task Parity Contract

This note records the lesson from building the BattleSnake and Halite Harbor
tasks. The goal is to prevent drift between the normal RevengeBench path and
the Harbor artifact path as we add more games.

## Core Contract

Harbor tasks may change the scaffold, but they must not change the benchmark
semantics.

Acceptable Harbor-specific scaffold:

- Docker image layout.
- Sealed target/opponent file permissions.
- `sudo run_probe` instead of the normal MCP `run_probe` tool.
- Task-owned `/workspace/.probe_budget` enforcement inside `sudo run_probe`.
- Root-only verifier files and hidden labels.
- Minor command glue needed to run inside one container.
- Extra Harbor-only metadata such as `probes_remaining`.

Not acceptable to duplicate or drift:

- Target/opponent selection.
- Initial editable starter code.
- Initial trace data semantics.
- Probe trace pair semantics.
- Offline scoring loop.
- Action parsing and action distance.
- Submission validation rules.
- Game engine invocation semantics, including game args and player ordering.
- Final `traces.json` / `eval.json` metric meaning.

If Harbor has to adapt execution, the shared repo code should still own the
meaning of the data and score.

## Gold Standard Pattern

BattleSnake is the current reference pattern.

The Harbor verifier does not implement its own benchmark scoring. It supplies a
subprocess-backed learner action provider and delegates the parser, distance
metric, aggregation, and summary construction to shared repo code in
`revenge_bench.traces.offline_eval`.

For new games, copy this architecture:

1. Keep game semantics in shared `src/revenge_bench/...` code.
2. Let Harbor scripts adapt only filesystem/process/container details.
3. Add parity tests that compare normal path output to Harbor/shared output on
   the same synthetic traces.

## Required Checks For Each Game

Before calling a Harbor game task parity-clean, verify these.

### 1. Task Instance Selection

Target and opponent pools must resolve exactly as in the normal config path.

Required:

- Test target identity.
- Test opponent list identity.
- Test `sims_per_round`, seed, and relevant task config values.

### 2. Prompt Information

The learner must receive the same task information as normal path, except for
mechanical Harbor scaffold changes.

Allowed differences:

- `/workspace` paths instead of normal logs paths.
- `sudo run_probe` instead of MCP `run_probe`.
- Single-session Harbor mechanics.

Required:

- Prompt parity tests against the native prompt renderer.
- Explicit tests that normal-only mechanics are absent from Harbor prompts.
- Explicit tests that Harbor-only mechanics are present.
- No wording that implies a Harbor-specific starter, stub, dummy policy, or
  easier baseline unless the normal path uses the exact same starter.

### 3. Initial Editable Starter

The learner's starting code is benchmark semantics. Harbor must not replace the
normal arena starter with a simpler, deterministic, or custom placeholder.

This caused real drift:

- BattleSnake normal path starts from the CodeClash starter that avoids moving
  backward and chooses randomly among safe moves. Harbor had briefly used an
  always-`up` placeholder, which changed round-0 behavior.
- Halite normal path starts from the CodeClash `MyCBot` random starter. Harbor
  had briefly used an all-STILL starter, which made the target look much easier
  and contaminated the result.

Required:

- Stage the exact same starter files the normal arena image gives to the
  editable learner.
- Preserve helper files needed by that starter, not just the main entry file.
- Add a parity guard for the starter, ideally byte-identical. If byte identity
  is not practical, use a hash or explicit full-file fixture and document why.
- Generate initial `traces.json` from that same starter, never from a Harbor-only
  stub.
- Prompt text must describe it as the starter/submission copy, not as a Harbor
  stub or dummy.

Do not treat a better round-0 Harbor distance as success until starter parity
has been checked.

### 4. Initial Traces

Visible initial data must match normal path semantics.

Required:

- Same learner starter policy as normal path.
- Same opponent pool.
- Same sim allocation per opponent.
- Same replay/trace parser meaning.
- Same target-observed state/action data.
- No hidden target/opponent source readable by the learner.

If exact normal orchestration cannot be reused, write tests proving generated
trace artifacts are semantically equivalent.

### 5. Probe Traces

Harbor may use `sudo run_probe`, but the probe output semantics must match the
normal interventionist path.

Required:

- Probe count control must live in the task image, not in a custom Harbor
  agent. The Docker image should bake `/workspace/.probe_budget` with root-owned
  readable permissions, and `sudo run_probe` must read, decrement, and enforce
  it before running trusted target code.
- `sudo run_probe` must be the only sudoers entry needed for agent-facing
  probes. A generic Harbor agent should be able to run the task by editing the
  probe artifact and executing `sudo run_probe`.
- Custom bridge agents may report or observe probe usage for telemetry, but
  they must not seed, reset, or redefine the task probe budget. Older bridge
  kwargs such as `max_probes` should be compatibility no-ops if retained.
- Shared parser/helper for converting replay files into probe `(state, action)`
  pairs, or a byte-identical parity test if tiny glue remains duplicated.
- Same `probe_action`, `target_action`, `distance`, and `target_state` meanings.
- Harbor-only additions, such as `probes_remaining`, must be additive only.

BattleSnake already follows this mostly through shared parser functions. Halite
now has shared `build_probe_trace_payload` / `extract_probe_state_action_pairs`
helpers and a byte-identical parity test.

### 6. Offline Evaluation

This is the most important part. Harbor must not own an independent scoring
loop.

Required:

- Shared evaluator in `revenge_bench.traces.offline_eval` or equivalent shared
  repo code.
- Normal tournament path calls the same evaluator.
- Harbor verifier calls the same evaluator through an execution adapter.
- Byte-identical parity test comparing normal path summary and Harbor/shared
  summary on the same traces.

The authoritative metric is `mean_distance`. Harbor `reward.txt` may be a
monotone presentation transform, but it must not define a new benchmark score.

### 7. Submission Validation

Validation differences can change which learner submissions are scoreable, so
they are benchmark semantics, not just scaffold.

Required:

- Shared validation/compile helper where possible.
- Same supported language detection.
- Same behavior for multiple `main.*` files.
- Same compile timeout policy unless explicitly justified.
- Same smoke/self-match validation if normal path does it.

This is still an open parity item for Halite.

### 8. Game Engine Invocation

Engine command construction must match normal path behavior.

Required:

- Same executable.
- Same game args.
- Same replay/log semantics.
- Same player ordering policy.
- Same randomization/shuffle semantics, or a documented/proven equivalent.
- Same target identity mapping semantics. For games that write package/team maps
  such as RoboCode `_pkg_to_agent.json`, do not vary the target alias across
  opponent subdirectories unless the shared normal-path scorer resolves aliases
  per simulation/opponent.
- Trace generators must fail on nonzero engine exits, empty trace files, or
  unparsable replay output. Never suppress stderr and bake an image with empty
  labels; that creates a false benchmark artifact.

This is still an open parity item for Halite.

## Red Flags

Treat these as signs the Harbor task may be drifting:

- A Harbor script contains a scoring loop that looks like a copy of
  `inverse_strategy.py`.
- A Harbor script computes `mean_distance` itself instead of calling shared code.
- A Harbor script has its own action parser.
- Harbor metadata has different field names for the same normal-path object.
- Harbor accepts a submission normal path would reject.
- Harbor runs the engine with different args or player order.
- Harbor uses a `stub_*`, always-still, always-up, dummy, or simplified starter
  when the normal path starts from richer arena-provided code.
- Harbor relies on a custom agent bridge to seed/reset `.probe_budget`; this
  prevents normal Harbor agents from being the primary artifact path and can
  cause different runs to have different probe semantics.
- Harbor round-0 distance is surprisingly better than the normal path before
  proving starter parity.
- Harbor round-0 `traces.json` has missing `mean_distance`, zero simulations,
  empty sim files, or an error payload after the image build.
- Prompt text says "stub" or "dummy" for the editable starter unless the normal
  path uses that exact same term and code.
- A task is declared done without a parity test.

## Review Checklist

For each new game, answer yes before shipping:

- Does normal path call shared scoring code?
- Does Harbor verifier call the same scoring code?
- Is there a byte-identical eval parity test?
- Is the editable starter identical to the normal arena starter?
- Is there a starter parity guard?
- Are probe pair semantics shared or byte-identically tested?
- Is submission validation shared or parity-tested?
- Is engine invocation shared or parity-tested?
- Are target and opponents hidden from the learner?
- Does the learner see no final labels/verifier data?
- Is every difference explainable as Harbor scaffold only?

If any answer is no, the task can be runnable, but it should not be called
parity-clean yet.
