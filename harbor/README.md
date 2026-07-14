# Running RevengeBench Tasks With Harbor

This directory contains self-contained
[Harbor](https://github.com/harbor-framework/harbor) tasks for RevengeBench.
Each task packages one sealed inverse-strategy problem: the agent can inspect
the task workspace, use the bounded `run_probe` oracle, and submit code that is
scored by the task verifier.

These Harbor tasks are an artifact format for running RevengeBench with Harbor.
They are separate from the main RevengeBench pipeline.

## Requirements

- Docker
- Harbor
- Credentials for the model provider used by your Harbor agent

Install Harbor in the environment you will use to launch runs. For example:

```bash
uv tool install harbor
```

Run the commands below from this directory:

```bash
cd harbor
```

## Run With a Published Image

Once RevengeBench task images are published, Harbor can pull the image named in
the task's `task.toml` automatically. For example:

```bash
export OPENAI_API_KEY=...

harbor run \
    -p tasks/battlesnake-gpt5-t09-gpt5-9aa36d603153-v0 \
    -a codex \
    -m gpt-5.4-mini \
    --allow-agent-host api.openai.com
```

The task image disables general internet access. `--allow-agent-host` only lets
the Harbor agent process reach the model API host; it does not give the task
container open internet access.

You can also use the example config:

```bash
harbor run -c run.yaml
```

The images have not been pushed yet. Until they are available remotely, use the
source-build path below.

## Build From Source

For local source builds, stage the task's Docker build context first:

```bash
./tasks/battlesnake-gpt5-t09-gpt5-9aa36d603153-v0/build_context.sh
```

Then run Harbor with `--force-build`:

```bash
harbor run \
    -p tasks/battlesnake-gpt5-t09-gpt5-9aa36d603153-v0 \
    -a codex \
    -m gpt-5.4-mini \
    --allow-agent-host api.openai.com \
    --force-build
```

The build context includes the task Dockerfile, target/opponent assets, and a
local `revenge_bench` wheel under `environment/wheels/`. If you change task
metadata, scoring code, trace parsing, prompts, or staged assets, rerun the
task's `build_context.sh` before building again.

## Running a No-Op Smoke Test

Use Harbor's `nop` agent to check that a task builds and verifies without
spending model calls:

```bash
./tasks/battlesnake-gpt5-t09-gpt5-9aa36d603153-v0/build_context.sh

harbor run \
    -p tasks/battlesnake-gpt5-t09-gpt5-9aa36d603153-v0 \
    -a nop \
    --force-build
```

This tests the packaged starter workspace and verifier path. It is not an agent
solving run.

## Task Layout

Each task directory contains:

| Path | Purpose |
| --- | --- |
| `task.toml` | Harbor task metadata, resource limits, and Docker image name. |
| `instruction.md` | Agent-facing task instructions. |
| `environment/` | Docker build context and trusted task runtime files. |
| `tests/` | Verifier entry point run by Harbor after the agent finishes. |
| `build_context.sh` | Rebuilds the local source-build context for that task. |

Runtime outputs are written under `harbor/jobs/` and are ignored by Git.

## Generating or Restaging Tasks

The repository includes one task per benchmark target. Maintainers can
regenerate the task set with:

```bash
uv run python -m revenge_bench.harbor.materialize --force
```

To regenerate and stage local source-build contexts for all tasks:

```bash
uv run python -m revenge_bench.harbor.materialize --force --stage
```

For a smaller subset:

```bash
uv run python -m revenge_bench.harbor.materialize --game robotrumble --target-count 2 --force --stage
```

## Security Model

Each task uses a single-container sealed-target design:

- The agent runs as the non-root `agent` user in `/workspace`.
- The target is sealed at `/target` and is readable only by root.
- Agents interact with the target through the bounded `sudo run_probe` oracle.
- The verifier runs after the agent session and scores held-out behavior.
- General task internet access is disabled.

The Harbor tasks are intended to expose the same inverse-strategy problem shape
as the main benchmark while making it easier to run with Harbor-compatible
agents and scaffolds.
