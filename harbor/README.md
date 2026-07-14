# RevengeBench × Harbor (Tier I)

This directory packages RevengeBench's inverse-strategy evaluation as
self-contained [Harbor](https://github.com/harbor-framework/harbor) tasks. It is
**purely additive** — nothing in the core `revenge_bench` package depends on it,
and no existing tournament or agent code is modified. The layout mirrors how
MLS-Bench keeps its Harbor packaging separate from the main library.

## Contents

| Path | Purpose |
| --- | --- |
| `harbor_agent.py` | Optional entry-point shim. Lazily exposes `HarborRevengeAgent` (implemented in `revenge_bench.harbor.agent`) for internal parity runs. Public artifact runs use normal Harbor agents such as `codex`. |
| `run.yaml` | Example Harbor job config (`harbor run -c run.yaml`) for the public built-in `codex` agent path. |
| `tasks/*-gpt5-9aa3-v0/` | Deployable, sealed interactive inverse-strategy tasks (Dockerfile, `task.toml`, `run_probe` oracle, verifier `tests/`). |

## Generating the full task set

The five `*-gpt5-9aa3-v0` directories are the manually audited pilot templates,
one per game. The canonical public task set is generated from the same
normal-path top-15 target selection used by the benchmark:

```bash
uv run python -m revenge_bench.harbor.materialize --force
```

This creates `5 x 15 = 75` concrete task directories under `harbor/tasks/`,
with unique `task.toml` names/images and `task_config.json` values. By default
it does not stage duplicated target/opponent files into every Docker context.
When preparing images, add `--stage`:

```bash
uv run python -m revenge_bench.harbor.materialize --force --stage
```

For quick checks or a single game:

```bash
uv run python -m revenge_bench.harbor.materialize --game robotrumble --target-count 2 --force
```

## Source-build fallback

The intended public path is to pull prebuilt task images once they are published
to Docker Hub. If you instead want Harbor or Docker to build a task image from
this repository, first stage the local build context for that task:

```bash
./tasks/battlesnake-gpt5-t09-gpt5-9aa36d603153-v0/build_context.sh
harbor run -p tasks/battlesnake-gpt5-t09-gpt5-9aa36d603153-v0 -a nop --force-build
```

For the whole generated task set, stage during materialization:

```bash
uv run python -m revenge_bench.harbor.materialize --force --stage
```

This matters because generated Docker contexts do not fetch `revenge_bench` from
PyPI. They install the wheel staged under each task's `environment/wheels/`, plus
the staged target/opponent assets under `environment/staging/`. Building from an
unstaged or stale context can produce images whose verifier imports fail, even
though the task directory itself looks complete. Rerun the task's
`build_context.sh` after changing Harbor scoring, trace parsing, prompts, task
metadata, or target/opponent staging.

## Security model

Each task uses the single-container, Unix-user sealing design proven in
AgenticPIC:

- The **agent** runs as the non-root `agent` user (UID 1000) in `/workspace`.
- The **target** is sealed at `/target` (`root:root`, mode `0700`) and is
  reachable only through `sudo run_probe`, a budget-limited oracle that runs the
  agent's probe code unprivileged and the trusted target as root, on random
  loopback ports never revealed to the agent.
- The probe budget is task-owned. Each image bakes `/workspace/.probe_budget`,
  and `sudo run_probe` is responsible for decrementing/enforcing it. Agents and
  agent bridges do not seed or reset the budget.
- Scoring is offline and separate: the verifier (`tests/test.sh`) generates
  hidden target-vs-opponent traces, asks the learner policy for actions via an
  unprivileged artifact runner, and emits a reward.

`HarborRevengeAgent` itself runs **outside** the container and drives the task
through Harbor's `BaseEnvironment.exec()`, adapting the async environment to the
synchronous interface expected by mini-swe-agent's `DefaultAgent`. It is optional
and exists for RevengeBench/mini-swe-agent loop parity; probe control stays in
the task image either way.

## Environment setup

Harbor and `revenge_bench` must be importable in the same Python environment.
Two supported options:

1. **Inject `revenge_bench` into the Harbor tool environment** (keeps Harbor as
   a `uv` tool):

   ```bash
   uv tool install harbor --with /Users/babak/vs_code/revenge-bench
   ```

2. **Install Harbor into the project `.venv`** alongside `revenge_bench`:

   ```bash
   uv pip install harbor
   ```

Either way, run Harbor commands from *this* `harbor/` directory so the
`harbor_agent` shim is on `sys.path`.

## Running

```bash
cd harbor

# Provider credentials follow normal Harbor practice: export them in the
# launching shell. Do not hard-code secrets in task files or run configs.
export OPENAI_API_KEY=...

# Using the example job config, equivalent to the command below:
harbor run -c run.yaml

# Public Harbor-style run with a built-in Harbor agent:
harbor run \
    -p tasks/battlesnake-gpt5-9aa3-v0 \
    -a codex \
    -m gpt-5.4-mini \
    --allow-agent-host api.openai.com

# Optional internal parity run via the RevengeBench bridge:
harbor run \
    -p tasks/battlesnake-gpt5-9aa3-v0 \
    -a harbor_agent:HarborRevengeAgent \
    -m openai/gpt-5 \
    --agent-kwarg "step_limit=150"
```

The task images keep general internet disabled. `--allow-agent-host
api.openai.com` is a narrow egress exception for the Harbor agent's model API
traffic only; it is not a task-level open-internet grant. If you prefer local
dotenv files during development, `--env-file ../.env` is equivalent to exporting
`OPENAI_API_KEY` before launching Harbor.

### Agent kwargs

`HarborRevengeAgent` accepts the following `--agent-kwarg` (`--ak`) values:

| Kwarg | Default | Meaning |
| --- | --- | --- |
| `step_limit` | `150` | Max think→command steps. |
| `cost_limit` | `5.0` | Max model spend (USD). |
| `api_base` | env | Override the model API base URL. |
| `api_key` | env | Override the model API key. |
| `reasoning_effort` | `medium` | Reasoning effort for capable models. |

The model is selected with `-m/--model` and passed through to mini-swe-agent's
`get_model`.

Older bridge commands that pass `max_probes` are accepted for compatibility, but
the value is ignored. The authoritative probe budget is the one baked into the
task image and enforced by `sudo run_probe`, matching the AgenticPIC-style
artifact pattern.
