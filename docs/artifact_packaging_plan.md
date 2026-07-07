# RevengeBench → Low-Barrier Dataset Artifact — Plan

Status: draft / design note
Branch: `feature/harbor-agent-support`
Goal: package RevengeBench so that anyone can run it with a small barrier
(ProgramBench-style: `pip install` + docker, pull image, score a submission),
despite RevengeBench's evaluation being sim-based and multi-agent by nature.

---

## 0. TL;DR

- **Scoring** is **open-loop**: the learner's hypothesized policy is queried on
  the **target's frozen `(state, action)`** states and compared via
  `actions_distance`. The learner never plays live against the opponent during
  scoring. This part is freezable → static hidden labels.
- **BUT elicitation is closed-loop.** The interventionist tournament
  (`InverseStrategyInterventionistTournament`) gives the agent a **probe**
  mechanism: during the edit phase the agent submits arbitrary *probe code*
  that plays a **LIVE simulation against the target** in a probe arena and
  returns `probe_traces` immediately. The agent chooses probe policies
  **adaptively**, so the target's responses **cannot be fully precomputed**.
- Consequence for packaging: a downloadable artifact must ship the **target as
  a sealed, queryable black-box oracle** (respond to arbitrary probe policies
  live, but never reveal its code), PLUS the frozen `(state, action)` labels for
  scoring. It is not "static labels only."
- The path is still mostly **packaging / refactoring**, but the barrier is
  higher than ProgramBench: (a) extract the offline evaluator, (b) freeze
  scoring labels, (c) **seal the target + a probe-sim runtime into the eval
  image**, (d) thin CLI + manifest.

---

## 1. The core finding (why this is feasible)

Current per-round pipeline (`InverseStrategyTournament.run()` in
`src/revenge_bench/tournaments/inverse_strategy.py`):

1. **Edit phase** — learner (mini-swe / Codex) edits its policy code in its own
   container. Only the learner edits. In the **interventionist** variant the
   agent may also **probe** here (see §1a).
2. **Simulation phase** — a **live match** runs
   `game_agents = [target_agent, opponent_agent]`. The learner does **NOT**
   play (`"Learner does NOT play in simulations"`). This produces the target's
   `(state, action)` traces (`sim_*.jsonl` / `*.hlt` / `record_*.xml` / …).
3. **Evaluation phase (offline)** — `_process_traces()` loads the learner's
   edited policy and, for each `(target_state, target_action)`, computes
   `learner_action = learner_code(target_state)` and
   `distance = actions_distance(learner_action, target_action)`.
   Mean action distance (lower is better) is the score.

Key consequence: **scoring a learner is a pure, offline function** of
`(learner_policy, frozen_target_traces)`. The live engine is spent on the
*target*, only to generate states — not on the learner. The scoring surface is
essentially ProgramBench's `eval(artifact) → score` shape already.

### 1a. The probe / elicitation loop (closed-loop, needs a LIVE target)

Source: `src/revenge_bench/tournaments/inverse_strategy_interventionist.py`.

- During the edit phase the agent runs `echo "PROBE_SUBMIT"` (mini-swe) or the
  MCP `run_probe` tool (Codex). This triggers `_run_inline_probe()`.
- The probe is auto-seeded from the learner's current submission
  (`_seed_probe`); the agent edits the probe policy, then submits it.
- `_execute_probe()` runs a **live simulation of the learner's probe policy vs
  the target** in a dedicated **probe arena** container
  (`sims_per_probe`, default 3), dispatched per game
  (`_execute_battlesnake_probe`, `_execute_halite_probe`,
  `_execute_huskybench_probe`, `_execute_robotrumble_probe`,
  `_execute_robocode_probe`). It reads the target's code live from the
  **target container** (e.g. `cat /workspace/main.py`) and pits probe-vs-target.
- `_parse_probe_traces_from_arena()` parses the game replay and the traces are
  written back into the learner container as an immediate observation.
- Budget: `max_probes_per_round` (default 5), `sims_per_probe` (default 3).
- End-of-round simulation is STILL target-vs-opponent (unchanged); scoring is
  STILL open-loop distance on the learner's submission.

**Why this breaks "static labels only":** the agent picks probe policies
adaptively based on prior probe feedback, so you cannot enumerate/precompute the
target's responses ahead of time. Probing requires a **live target that answers
arbitrary probe policies**. To distribute the benchmark you must ship the target
as a **sealed black-box oracle** inside the eval image — queryable via probe
simulations, but with its code hidden from the agent.

---

## 2. Per-game execution matrix (offline evaluation substrate)

How the learner's hypothesized policy is actually executed during offline
evaluation is **heterogeneous per game** (verified in `inverse_strategy.py`):

| Game | Execution mode | Isolation |
|---|---|---|
| BattleSnake | host `importlib` load of `move()` (`_load_learner_module`) | in-process, host |
| RoboCode | host `importlib` load of `move()` | in-process, host |
| Halite3 | host `importlib` load of `move()` | in-process, host |
| HuskyBench | host `importlib` load of a `Bot` subclass, instantiated | in-process, host |
| Halite I | compile bot on host → query via `subprocess` (`query_compiled_bot`) | separate process |
| RobotRumble | run `robot.js` inside `node:18-alpine` via `run_js_eval` | Docker / Singularity container |

Invariant across all six: **open-loop replay** — feed frozen target states to
the policy, read one action, compare to the target's recorded action. The
execution substrate (in-process import / subprocess / container) is a per-game
detail, **not** part of the metric.

RobotRumble already provides the container-sandboxed template (`run_js_eval`);
the four Python-import games would need the same treatment (run inside the
per-arena image) to make the whole suite uniformly sandboxed.

Pluggable scoring core per game: `extract_state_action_pairs` +
`actions_distance` (in `src/revenge_bench/traces/parsers/<game>.py`).

---

## 3. Mapping to ProgramBench

| ProgramBench | RevengeBench equivalent |
|---|---|
| Submission = `submission.tar.gz` (codebase) | Submission = **final learner policy file(s)** |
| Hidden labels = per-branch test suite (in eval image) | Hidden labels = **target's `(state, action)` traces on a frozen state set** |
| `eval(tarball)` = build + run tests → pass rate | `eval(policy)` = **replay policy on frozen states** → mean action distance |
| Task image `programbench/<task>:v6` | Per-arena image bundling engine/SDK + replay harness + frozen target traces **+ sealed target oracle** (for probing) |
| `programbench eval run/` | `revengebench eval run/` |
| Tier0 / Tier1 verify | recompute distance from stored per-state results / re-replay in Docker |
| *(no analog — ProgramBench has no live oracle)* | **Probe service**: sealed target answering arbitrary probe policies live |

The scoring sims move **offline, one-time, to label generation** (run the
tournament once per instance to harvest the target's traces), like ProgramBench
pre-bakes hidden tests. **The probe sims cannot be pre-baked** — they need the
live sealed target inside the eval image (§1a).

---

## 4. The metric fork (decide this first — it gates everything)

- **Regime A — open-loop action-matching (current):** query the learner on the
  target's own states; compare actions. Pure, cheap, deterministic, packageable.
  Needs an **execution runtime** but **no live opponent/match**.
- **Regime B — closed-loop behavioral equivalence:** the learner controls the
  trajectory; opponent reacts; judge state-visitation / outcome vs target.
  Requires **live engine + opponent + multi-container**. Not a pure artifact.

RevengeBench currently commits to **Regime A**. Known limitation to acknowledge
in the paper: open-loop only tests states the *target* visited (off-distribution
/ compounding-error blind spot). Options:

- Ship **A** as the public, low-barrier artifact (recovery-fidelity metric).
- Optionally keep **B** as a heavier verified leaderboard track, and **report
  how tightly A correlates with B** so the public proxy is trustworthy.

---

## 5. Build plan (concrete steps on this repo)

### Step 1 — Extract a pure evaluator (linchpin)
Factor the body of `run_evaluation_phase` / `_process_traces` into a
standalone, tournament-independent module:

```
evaluate_policy(policy_path, target_traces, game) -> {mean_action_distance, per_state, per_sim}
```

- No dependency on the tournament, opponent agents, or live containers.
- Reuse the existing per-game `extract_state_action_pairs` + `actions_distance`.
- Add a unit test with a tiny fixed trace + a trivial policy.
- This single refactor also unlocks the OpenEvolve-as-Player and
  Harbor-flatten paths (they all need the same pure evaluator).

### Step 2 — Freeze the scoring label set
- Run the tournament once per `(arena, target)` to mint the target's traces.
- **Split states**: a **public dev set** (agent may query during inference) and
  a **hidden test set** (only inside the eval image), to prevent overfitting —
  mirroring ProgramBench's hidden tests.
- Pin seeds so the frozen set is reproducible. Store target actions for both.
- Note: this covers **scoring only**. The **probe loop** cannot be frozen this
  way (Step 2b).

### Step 2b — Seal the target as a black-box probe oracle
- The interventionist elicitation loop needs a **live target** that answers
  arbitrary, adaptively-chosen probe policies (§1a).
- Ship the target inside the eval image as a **sealed oracle**: its code is
  present but unreadable by the agent (separate container / obfuscated /
  behind a probe-sim service), exposing only `run_probe(probe_policy) ->
  probe_traces`.
- Enforce the probe budget (`max_probes_per_round`, `sims_per_probe`) in the
  service so a submission can't exfiltrate the target by brute-force querying.
- Reuse the existing per-game `_execute_<game>_probe` runners as the service
  backend.

### Step 3 — Define the submission layout
```
run/<arena>__<target>/
  submission/           # or submission.tar.gz
    policy.py           # (or robot.js / compiled source, per game)
```
Bring-your-own-agent: anything that emits the policy qualifies (mini-swe,
Codex, OpenEvolve, human).

### Step 4 — Package per-arena eval images
- Image bundles: arena engine/SDK + offline replay harness + **hidden target
  traces** + scoring entrypoint + **sealed target probe oracle** (Step 2b).
- Uniformly sandbox the learner call inside the image (RobotRumble's
  `run_js_eval` is the template; extend to the Python-import games).
- Isolate the sealed target so the agent cannot read its code, only query it.
- Push to a registry; pull on demand. Scoring labels can live on HuggingFace and
  download on demand (ProgramBench `blob sync` model); the sealed target ships
  inside the image, not as a public blob.

### Step 5 — Thin CLI + manifest + verify tiers
- `revengebench eval run/`: iterate instances, inject each policy into the
  image, replay, write `<iid>.eval.json`, print a summary.
- Dataset manifest (instances list) + HF dataset for labels/blobs.
- Tier0 (recompute distance from stored per-state results) and Tier1 (re-replay
  in Docker) for leaderboard integrity.

---

## 6. Design decisions / gotchas

- **Keep open-loop as the shippable SCORING metric** (Regime A). Full
  closed-loop self-play scoring is not deterministically packageable.
- **Two distinct target surfaces, don't conflate them**:
  - *Scoring* uses only the target's **precomputed actions** (static labels).
  - *Probing/elicitation* needs the **live sealed target oracle** (§1a, Step 2b)
    — the agent queries it but never reads its code.
- **Target stays hidden while queryable**: never expose target code; expose
  static labels for scoring + a rate-limited probe service for elicitation. This
  preserves the "reverse-engineer a hidden policy" nature *and* allows public
  distribution.
- **Probe budget is a security boundary**: without the per-round/per-probe cap,
  a submission could query the oracle enough to reconstruct the target. Enforce
  it server-side in the eval image.
- **Iteration budget**: give agents the **public dev traces** as a practice
  signal during inference; score once on the **hidden test traces**
  (private-iterate → submit-artifact → score-once, like ProgramBench).
- **Determinism**: fix seeds and the frozen scenario set; the learner call is a
  function of the stored observation only.
- **Uniform sandboxing**: for a public artifact, run every game's policy call
  inside its per-arena container (untrusted code). Logic unchanged; substrate
  hardened.
- **What we give up**: live PvP/Elo leaderboard. **What we keep**: behavioral-
  recovery distance (the paper's core metric).

---

## 7. Open questions to resolve next

1. Is Regime A (action-agreement on target-visited states) sufficient for the
   paper's claim, or is trajectory control (Regime B) essential?
2. Exact contents of each game's frozen "label blob"
   (`sim_*` formats + `extract_state_action_pairs` output schema per game).
3. Dev/test split ratio and how many states/scenarios per instance.
4. Registry + HF layout and versioning tags (`task_*_vN`).
5. How to expose a **public inference/practice container** per instance (arena
   + dev signal) so agent developers have a low-barrier loop too.
6. Do we ship the probe/elicitation loop in the public artifact at all, or
   offer two tiers: (a) **static** (scoring labels only, no probing — fully
   ProgramBench-like, lowest barrier) and (b) **interactive** (sealed target
   oracle + probe budget — higher barrier, matches the interventionist paper
   setting)? This is the biggest packaging decision.
7. Sealing mechanism for the target oracle (separate container vs obfuscation)
   and how to make it tamper-resistant against a hostile submission.

---

## 8. Relationship to earlier agent-integration questions

The same pure evaluator (Step 1) is the linchpin for all three extensions
discussed:
- **Artifact / ProgramBench-style dataset** (this plan).
- **OpenEvolve as a `Player`** (needs a headless per-candidate evaluator).
- **Harbor flatten** (single-container task + hidden target labels + verifier).

Contrast of agent-coupling across benchmarks:
- **ProgramBench**: artifact-pure (`eval(tarball) → pass_rate`); most decoupled.
- **MLS-Bench**: narrow tool-waist (`edit/test/submit`) or Harbor packaging.
- **RevengeBench**: interactive/relational multi-agent. **Scoring** is open-loop
  action distance to a hidden target (freezable). **Elicitation** (interventionist
  variant) is closed-loop probing that needs a live sealed target oracle. This
  plan makes the *scoring* surface artifact-pure while confining the live sim to
  (a) one-time label generation and (b) a rate-limited, sealed probe oracle for
  the interactive tier.

---

## 9. Prior art: the AgenticPIC Harbor design (adopt this)

A parallel repo, `/Users/babak/vs_code/AgenticPIC`, **already implements Tier I**
as a Harbor integration — but for **photonic/scientific inverse-design tasks**
(MZI meshes, gratings, waveguides), not the six game arenas. Its design solves
every Tier I step, and two of them more elegantly than this plan proposed.
**Decision: build RevengeBench Tier I as AgenticPIC-style Harbor tasks, reusing
its sealing, security model, and packaging.**

### 9.1 Key architecture choice — single container, Unix-user sealing

Replace the multi-container / socket idea in §Step 2b/Step 4 with AgenticPIC's
model (all in ONE Harbor task container):

- Agent commands run as non-root user `agent` (UID 1000).
- The target lives at `/target/`, `root:root` mode `0700` — the agent user
  **cannot read it**. Sealing is filesystem permissions, not a separate image.
- Oracle/eval commands run as root (`execute_privileged`).

### 9.2 Probe oracle — `run_probe` sudoers script

`tasks/<task>/environment/run_probe`: agent runs `sudo /usr/local/bin/run_probe`.
Runs as root, reads `/target/`, enforces `/workspace/.probe_budget`
(decrement, block at 0), clears `PYTHONPATH`/`PYTHONHOME` to prevent import
hijacking, copies the request to a root-private dir, writes unique
`probe_results_{N}.json`. This is the sealed, rate-limited, anti-exfiltration
oracle §1a/Step 2b called for — cleanly done.

### 9.3 Evaluator — declarative `EvaluationPlan` with security validation

`picagent/harbor/evaluators.py`: the "pure evaluator" (Step 1) is a validated
recipe. `EvaluationStep` declares `user` / `executes_learner_code` /
`reads_target`; `_validate_plan` **refuses to run learner code as root**.
Two-phase: Phase A (agent user) runs learner → outputs; Phase B (root) runs
target → compares. `_runner_registry` maps a container-detected runner path to a
task-owned plan. `metrics.py` `normalize_eval_payload` turns task-specific JSON
into a task-agnostic metric envelope for the viewer.

### 9.4 Packaging — Harbor task format

`tasks/<task>_v0/`: `task.toml` (verifier/agent/environment timeouts, resources,
`docker_image`, `[verifier.env]` for credentials), `environment/Dockerfile`
(creates `agent` UID 1000, bakes starter scaffold + `.probe_budget`),
`tests/test.sh` (pytest → `/logs/verifier/reward.txt` 0/1), `solution/solve.sh`,
`oracle/`, `instruction.md`, `picagent_config.yaml` (verbatim prompts).

### 9.5 Agent bridge

`HarborPICAgent(BaseAgent)` (`picagent/harbor/agent.py`) runs **outside** the
container, bridging Harbor's async `exec()` → sync mini-SWE-agent via
`_HarborEnvAdapter`. Works on any TB2 task via `--agent-import-path`.

For RevengeBench Harbor support, this bridge pattern is optional rather than
the artifact contract. Probe limits should be enforced by the task image's
`sudo /usr/local/bin/run_probe` script, so built-in Harbor agents can run the
same task without a custom bridge. A bridge may preserve an internal
mini-swe-agent loop, but it must not seed/reset `.probe_budget` or redefine
probe semantics.

### 9.6 Gaps to close for RevengeBench games (the actual remaining work)

1. **No game arenas packaged.** `_runner_registry` only has 4 photonic runners;
   BattleSnake/Halite/RobotRumble/RoboCode/HuskyBench still live in the old
   `picagent/tournaments/inverse_strategy_interventionist.py` flow.
2. **Scoring model differs.** Harbor reward is pass/fail (`reward.txt` 0/1);
   RevengeBench's core metric is **continuous mean action distance**. Emit it in
   `eval.json` and route via `normalize_eval_payload`; decide continuous-score →
   leaderboard mapping (vs binary reward).
3. **Oracle provenance differs.** Photonic oracle = deterministic simulator;
   game oracle = live target-vs-opponent sim. The game `run_probe` must run the
   per-game `_execute_<game>_probe` engine (BattleSnake CLI, Halite binary,
   `node:18-alpine` for RobotRumble) inside the task container as root.

### 9.7 Revised build steps (supersedes §5 for Tier I)

Per game arena, reuse the `rectangular_mesh_mzi_v0` skeleton:
1. Copy `task.toml` + `Dockerfile` + `run_probe` sudoers + `tests/test.sh` +
   `EvaluationPlan` skeleton.
2. Port the game's probe oracle: wrap `_execute_<game>_probe` as the game's
   `run_probe` runner reading `/target/`.
3. Port the game's scoring: turn `_process_traces` + `actions_distance` into an
   `EvaluationPlan` (Phase A learner, Phase B root-target-compare) emitting
   `eval.json` with `mean_action_distance`.
4. Register each game in `_runner_registry` (mirror the photonic entries).
5. Freeze target/opponent traces + `.probe_budget` into the image; wire the
   continuous-distance → leaderboard mapping.
