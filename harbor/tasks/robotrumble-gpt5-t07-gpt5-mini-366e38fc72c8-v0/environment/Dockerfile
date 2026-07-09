# RevengeBench RobotRumble inverse-strategy task (Tier I, interactive).
#
# Build context: harbor/tasks/robotrumble-gpt5-9aa3-v0/environment/
# The target and sampled opponents are baked into the image but sealed
# root-only. The learner sees only visible round-0 traces and can query the
# sealed target through sudo run_probe.

FROM --platform=linux/amd64 ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    curl ca-certificates python3.10 python3.10-venv python3-pip \
    python-is-python3 wget git build-essential jq locales sudo ripgrep \
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

RUN git clone https://github.com/CodeClash-ai/RobotRumble.git /workspace \
 && cd /workspace \
 && git remote set-url origin https://github.com/CodeClash-ai/RobotRumble.git
WORKDIR /workspace

RUN useradd -m -s /bin/bash -u 1000 agent

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

COPY wheels/ /tmp/wheels/
RUN python3 -m pip install --no-deps /tmp/wheels/revenge_bench-*.whl \
 && python3 -m pip install pyyaml tqdm zstandard \
 && rm -rf /tmp/wheels \
 && python3 -I -c "from revenge_bench.traces.parsers import robotrumble; print('revenge_bench RobotRumble import OK')"

RUN mkdir -p /opt/robotrumble /opt/revengebench /target /logs/verifier /run

COPY generate_round_traces.py /opt/robotrumble/generate_round_traces.py
COPY generate_initial_traces_json.py /opt/robotrumble/generate_initial_traces_json.py
COPY score_robotrumble_submission.py /opt/robotrumble/score_robotrumble_submission.py
COPY robotrumble_action_runner.py /opt/robotrumble/robotrumble_action_runner.py
COPY run_probe_impl.py /opt/robotrumble/run_probe_impl.py
COPY run_probe /usr/local/bin/run_probe
RUN chmod 644 /opt/robotrumble/*.py \
 && chmod 755 /usr/local/bin/run_probe \
 && echo "agent ALL=(root) NOPASSWD: /usr/local/bin/run_probe" > /etc/sudoers.d/probe \
 && chmod 440 /etc/sudoers.d/probe

COPY staging/target/ /target/
COPY staging/resolved_task.json /target/resolved_task.json
COPY staging/instruction.md /workspace/instruction.md
COPY staging/opponents/ /opt/revengebench/opponents/

COPY starter_robot.js /workspace/robot.js
RUN echo 25 > /workspace/.probe_budget \
 && chown root:root /workspace/.probe_budget \
 && chmod 644 /workspace/.probe_budget \
 && python3 -I /opt/robotrumble/generate_round_traces.py \
 && python3 -I /opt/robotrumble/generate_initial_traces_json.py \
 && find /workspace/rounds -name '_target_*' -delete \
 && cp /workspace/robot.js /workspace/probe.js \
 && chown -R root:root /target /opt/revengebench/opponents /workspace/rounds \
 && chmod 700 /target \
 && chmod 700 /opt/revengebench /opt/revengebench/opponents \
 && chmod -R go-rwx /opt/revengebench/opponents \
 && chmod -R a+rX /workspace/rounds \
 && chmod -R a-w /workspace/rounds \
 && chown -R agent:agent /workspace/robot.js /workspace/probe.js /workspace/instruction.md /logs

USER agent
