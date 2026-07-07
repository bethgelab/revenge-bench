# Harbor Verifier Subprocess Guardrails

This note records the extra robustness contract for Harbor verifier adapters.
It complements `docs/harbor_task_parity_contract.md`.

## Why This Exists

In Harbor, the verifier often runs as root because it must read hidden labels,
sealed targets, and root-only verifier files. Learner code must never execute
with those privileges.

Therefore the verifier may need a subprocess-backed learner action provider:

- Root verifier reads hidden traces.
- Unprivileged learner subprocess receives only one state/query at a time.
- Learner subprocess returns an action.
- Shared repo scoring code computes distance and aggregation.

This subprocess bridge is Harbor scaffold. It must not define new benchmark
semantics.

## Core Rule

The verifier can see hidden data. Learner action code cannot.

Required:

- Run learner action code as the same unprivileged user used by the agent,
  normally `agent`.
- Never import or execute learner code in the root verifier process.
- Keep hidden labels, sealed targets, sealed opponents, and verifier output
  unreadable/unwritable by the learner subprocess.
- Treat the subprocess as an execution adapter only. Parsing, action distance,
  and summary metrics must remain shared repo code.

## Subprocess Uses

Do not confuse these categories.

### Game Orchestration

Running engines, compilers, bots, and live probe games uses subprocesses in both
normal and Harbor paths. This is ordinary arena plumbing.

Examples:

- BattleSnake starts HTTP bot servers and runs `battlesnake play`.
- Halite compiles/runs external bot executables.
- RobotRumble runs JS with Node and the game engine.
- RoboCode compiles Java and runs Robocode.
- HuskyBench starts the poker engine and client processes.

### Probe Oracle

`sudo run_probe` runs trusted root code that may spawn game processes. It should
adapt the normal interventionist probe path while keeping target source sealed.

Probe subprocesses are not final scoring. They produce visible
`probe_trace_*.json` evidence.

### Final Learner Query Bridge

This is the security-sensitive case.

The root verifier holds hidden traces and uses a subprocess/action-provider to
query learner code as an unprivileged user. Games may implement this differently:

- External-runtime games may naturally run learner code as a compiled binary or
  JS process.
- Python in-process-style games need an explicit bridge so root does not import
  learner code directly.

## Required Guardrails

### 1. Privilege Boundary

Required:

- Launch learner action code as `agent`, not root.
- Use an empty or minimal environment.
- Set only explicit safe variables such as `HOME`, `PATH`, `PYTHONNOUSERSITE`,
  and game-specific import paths.
- Keep verifier labels under a root-only path such as `/run/verifier_labels`.
- Keep sealed target/opponent code root-only.
- Keep verifier output directory root-owned unless Harbor requires otherwise.

Check:

- A smoke test should prove the agent cannot read target, opponents, or hidden
  labels.

### 2. Protocol Boundary

Required:

- Use a strict machine protocol, usually JSONL.
- Reserve learner subprocess stdout for protocol only.
- Redirect learner stderr to a verifier log file.
- Suppress or redirect learner stdout/stderr while invoking learner lifecycle or
  action methods.
- Malformed JSON must not crash the entire verifier. It should count as an
  invalid/missing action according to the shared scoring contract.
- Record protocol error counts in `eval.json` or a verifier-side log.

This matters because agents may print debugging output from imports,
constructors, lifecycle hooks, or action functions.

### 3. Timeout Boundary

Required:

- Startup/import timeout.
- Per-action timeout.
- Overall verifier timeout as a final backstop.
- Kill or restart the subprocess on a per-action timeout.
- Bound repeated failures so a broken learner cannot hang scoring forever.

Recommended counters:

- `startup_timeout_count`
- `action_timeout_count`
- `restart_count`
- `crash_count`

### 4. Crash And Exit Handling

Required:

- If the subprocess exits early, the verifier must degrade deterministically.
- Capture stderr in a file such as `learner-runner.stderr`.
- Do not let a crash silently remove hard examples from the denominator unless
  the normal path does the exact same thing.
- Include a concise failure summary in `eval.json` or verifier artifacts.

Recommended:

- Restart once for transient crashes if that matches the game semantics.
- After repeated crashes, score remaining actions as invalid according to the
  shared scoring policy.

### 5. Environment Parity

Required:

- Match the normal path's expected working directory.
- Match expected import/classpath/module paths.
- Use the same task image dependencies where possible.
- Run with the same source files the learner edited.
- Do not grant extra packages, paths, or permissions only in Harbor unless they
  are Harbor scaffold and cannot affect policy semantics.

For Python games, explicitly set `PYTHONPATH` or run from the expected code
directory. Avoid relying on ambient host environment.

### 6. State Parity

Required:

- Match normal path statefulness.
- If normal path uses one persistent learner instance for evaluation, Harbor
  should do the same.
- If normal path reloads per simulation or action, Harbor should do the same.
- Any difference must be documented and parity-tested.

Examples:

- HuskyBench normal evaluation uses a persistent loaded bot provider. Harbor
  should keep the same lifecycle behavior inside the subprocess.
- Stateless function games should not accidentally gain persistent state unless
  normal path does too.

### 7. Metric Integrity

Required:

- Learner failures must not improve score.
- Invalid/missing actions must have the same denominator behavior as normal
  path.
- If normal path currently skips missing actions, Harbor may match that for
  parity, but document it as a possible benchmark weakness.
- Every eval summary must report denominator audit counters:
  `expected_actions`, `scored_actions`, `skipped_none_actions`, and
  `skipped_none_fraction`. These counters make legacy skip behavior visible
  without changing historical score semantics.
- Prefer counting invalid/missing actions as max-distance when this is already
  the normal-path contract or can be safely moved into shared code.

Red flag:

- A broken subprocess gets a good `mean_distance` because only successful
  action queries were counted.

### 8. Shared Scoring

Required:

- Harbor verifier supplies an action provider only.
- Shared repo code owns replay parsing, state/action extraction, action
  normalization, action distance, aggregation, and `eval.json` metric meaning.
- Add a byte-identical parity test comparing normal-path evaluation and the
  shared/Harbor evaluation on the same fixed traces and fixed action provider.

## Tests To Add Per Game

At minimum:

- Good learner returns valid actions.
- Noisy learner prints during import/lifecycle/action and scoring still works.
- Crashing learner is recorded and does not crash the whole verifier.
- Hanging learner hits per-action timeout.
- Malformed JSON/action is counted consistently.
- Learner subprocess cannot read hidden labels, sealed target, or sealed
  opponents.
- Scoring parity test is byte-identical with normal path for a deterministic
  provider.

## Review Checklist

Before calling a Harbor verifier robust:

- Does root verifier avoid importing learner code directly?
- Does learner action code run as `agent`?
- Are hidden labels and sealed code unreadable by learner?
- Is stdout reserved for protocol and stderr logged separately?
- Are noisy prints from learner code contained?
- Are startup and per-action timeouts enforced?
- Are crashes and malformed responses counted and logged?
- Does missing/invalid action behavior match normal path?
- Are expected/scored/skipped action counters present in the eval summary?
- Does subprocess statefulness match normal path?
- Does shared repo code own final scoring semantics?
- Is there a parity test proving normal and Harbor scoring agree?

If any answer is no, the task can still be runnable, but the verifier bridge is
not fully hardened.
