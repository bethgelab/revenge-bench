# RevengeBench BattleSnake inverse-strategy task (Tier I, interactive).
#
# Extends the native BattleSnake arena image with AgenticPIC-style single-
# container Unix-user sealing so the target bot can be queried (bounded probe
# budget) but never read, and adds the offline scorer used by the Harbor
# verifier. Nothing in the core revenge_bench package is modified.
#
# Build context: harbor/tasks/battlesnake-gpt5-9aa3-v0/environment/
#   Dockerfile             <- this file
#   run_probe              <- trusted probe oracle
#   parse_probe_traces.py  <- trusted trace parser
#   generate_round_traces.py <- trusted normal-path trace generator
#   generate_initial_traces_json.py <- trusted normal-path initial scorer
#   wheels/                <- staged local revenge_bench wheel
#   staging/target/        <- staged sealed target bot (baked, root-only)
#   staging/opponents/     <- sampled opponent pool, root-only after trace generation
#   staging/instruction.md <- staged task instruction (root copy validates Harbor)
#
# The frozen scoring labels (tests/labels/sim_*.jsonl) are NOT baked here;
# Harbor mounts tests/ only at verification time so they stay hidden from the
# agent during its work session.

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    GO_VERSION=1.22.0 \
    PATH=/usr/local/go/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PIP_ROOT_USER_ACTION=ignore

# --- Base BattleSnake arena (mirrors arenas/battlesnake/BattleSnake.Dockerfile) -
# revenge_bench requires Python >=3.11, but ubuntu:22.04 ships 3.10. Pull 3.11
# from deadsnakes and make it the default `python3`/`python` on the hardened
# PATH. Both the probe oracle (run_probe) and the verifier (tests/test.sh)
# invoke `python3 -I` under PATH=/usr/local/bin:/usr/bin:/bin, so the 3.11
# interpreter must be reachable there (hence the /usr/local/bin symlinks). The
# distro's /usr/bin/python3 (3.10) is left untouched so apt/add-apt-repository
# keep working.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    curl ca-certificates wget git build-essential jq locales sudo ripgrep \
    software-properties-common gnupg \
 && add-apt-repository -y ppa:deadsnakes/ppa \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3.11-dev \
 && rm -rf /var/lib/apt/lists/* \
 && ln -sf /usr/bin/python3.11 /usr/local/bin/python3 \
 && ln -sf /usr/bin/python3.11 /usr/local/bin/python \
 && curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py \
 && python3.11 /tmp/get-pip.py \
 && rm /tmp/get-pip.py \
 && python3 -m pip install --upgrade pip

RUN ARCH=$(dpkg --print-architecture) \
 && curl -fsSL https://go.dev/dl/go${GO_VERSION}.linux-${ARCH}.tar.gz -o /tmp/go.tar.gz \
 && tar -C /usr/local -xzf /tmp/go.tar.gz \
 && rm /tmp/go.tar.gz

RUN git clone https://github.com/CodeClash-ai/BattleSnake.git /workspace
WORKDIR /workspace
RUN cd game && go build -o battlesnake ./cli/battlesnake/main.go
# --ignore-installed: some deps (e.g. blinker) are apt/distutils-installed in the
# shared /usr/lib/python3/dist-packages and cannot be cleanly uninstalled; install
# fresh into 3.11's site-packages, which takes precedence on sys.path.
RUN python3 -m pip install --ignore-installed -r requirements.txt

# --- Sealing user + scoring dependencies --------------------------------------
RUN useradd -m -s /bin/bash -u 1000 agent

# Harbor's built-in Codex agent runs a package-manager installer unless the
# Codex CLI is already available to the `agent` user. Bake it in at image build
# time so agent setup does not need apt/network access at runtime.
RUN su - agent -c 'set -euo pipefail; \
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash; \
    export NVM_DIR="$HOME/.nvm"; \
    . "$NVM_DIR/nvm.sh"; \
    nvm install 22; \
    nvm alias default 22; \
    npm install -g @openai/codex@latest; \
    codex --version' \
 && ln -sf /home/agent/.nvm/versions/node/$(ls /home/agent/.nvm/versions/node | sort -V | tail -1)/bin/node /usr/local/bin/node \
 && ln -sf /home/agent/.nvm/versions/node/$(ls /home/agent/.nvm/versions/node | sort -V | tail -1)/bin/npm /usr/local/bin/npm \
 && ln -sf /home/agent/.nvm/versions/node/$(ls /home/agent/.nvm/versions/node | sort -V | tail -1)/bin/codex /usr/local/bin/codex

# The scorer imports the REAL BattleSnake trace parser + the shared offline
# scorer (revenge_bench.traces.offline_eval) that the native tournament also
# uses. revenge_bench is NOT published to PyPI, so we install THIS working
# tree's build, staged as a wheel into the build context by build_context.sh
# (run it before `harbor run` / `docker build`). --no-deps keeps the image lean:
# the scorer + probe parser only need the wheel + zstandard at runtime.
COPY wheels/ /tmp/wheels/
RUN python3 -m pip install --no-deps /tmp/wheels/revenge_bench-*.whl \
 && python3 -m pip install zstandard \
 && rm -rf /tmp/wheels \
 && python3 -I -c "from revenge_bench.traces import offline_eval; from revenge_bench.traces.parsers import battlesnake; print('revenge_bench import OK')"

# --- Bake the sealed-target + probe oracle helpers ----------------------------
RUN mkdir -p /opt/battlesnake /opt/revengebench /target /logs/verifier /run \
 && cp /workspace/server.py /opt/battlesnake/server.py \
 && cp /workspace/game/battlesnake /opt/battlesnake/battlesnake \
 && chmod 755 /opt/battlesnake/battlesnake

COPY parse_probe_traces.py /opt/battlesnake/parse_probe_traces.py
COPY generate_round_traces.py /opt/battlesnake/generate_round_traces.py
COPY generate_initial_traces_json.py /opt/battlesnake/generate_initial_traces_json.py
COPY run_probe /usr/local/bin/run_probe
RUN chmod 644 /opt/battlesnake/parse_probe_traces.py \
 && chmod 644 /opt/battlesnake/generate_round_traces.py \
 && chmod 644 /opt/battlesnake/generate_initial_traces_json.py \
 && chmod 755 /usr/local/bin/run_probe \
 && echo "agent ALL=(root) NOPASSWD: /usr/local/bin/run_probe" > /etc/sudoers.d/probe \
 && chmod 440 /etc/sudoers.d/probe

# --- Sealed target bot: readable/runnable only by root ------------------------
COPY staging/target/ /target/
COPY staging/resolved_task.json /target/resolved_task.json

# --- Probe budget: root-owned so the agent can read but not reset it ----------
RUN echo 25 > /workspace/.probe_budget \
 && chown root:root /workspace/.probe_budget \
 && chmod 644 /workspace/.probe_budget

# --- Agent-facing workspace: starter bot + a copy-of-your-bot probe seed -------
# The starter (and its probe.py copy) are self-contained Battlesnake server bots
# so `run_probe` can launch them via `python main.py` (server.py sits alongside
# in /workspace). The offline scorer imports main.py and calls move() directly.
COPY staging/instruction.md /workspace/instruction.md
COPY staging/opponents/ /opt/revengebench/opponents/
COPY starter_main.py /workspace/main.py
RUN python3 -I /opt/battlesnake/generate_round_traces.py \
 && python3 -I /opt/battlesnake/generate_initial_traces_json.py \
 && chown -R root:root /target /opt/revengebench/opponents /workspace/rounds \
 && chmod 700 /target \
 && chmod 700 /opt/revengebench /opt/revengebench/opponents \
 && chmod -R go-rwx /opt/revengebench/opponents \
 && chmod -R a+rX /workspace/rounds \
 && chmod -R a-w /workspace/rounds
RUN cp /workspace/main.py /workspace/probe.py \
 && chown -R agent:agent /workspace/main.py /workspace/probe.py /workspace/instruction.md /logs

# The agent owns its editable game scaffolding but NOT the sealed target/budget.
RUN chown -R agent:agent /workspace/game /workspace/server.py 2>/dev/null || true

USER agent
