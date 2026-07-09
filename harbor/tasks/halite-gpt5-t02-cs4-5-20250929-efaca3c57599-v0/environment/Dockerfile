# RevengeBench Halite inverse-strategy task (Tier I, interactive).
#
# Build context: harbor/tasks/halite-gpt5-9aa3-v0/environment/
# The target and sampled opponents are baked into the image but sealed
# root-only. The learner sees only visible round-0 traces and can query the
# sealed target through sudo run_probe.

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    curl ca-certificates wget git build-essential jq locales sudo ripgrep \
    software-properties-common gnupg ocaml ocamlbuild python-is-python3 \
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

RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

RUN git clone https://github.com/CodeClash-ai/Halite.git /workspace \
 && cd /workspace \
 && git remote set-url origin https://github.com/CodeClash-ai/Halite.git \
 && cd environment \
 && make
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
 && python3 -I -c "from revenge_bench.traces.parsers import halite; print('revenge_bench Halite import OK')"

RUN mkdir -p /opt/halite /opt/revengebench /target /logs/verifier /run \
 && HLT_HEADER="$(find /workspace -name hlt.h -print -quit)" \
 && test -n "$HLT_HEADER" \
 && cp "$HLT_HEADER" /opt/halite/hlt.h \
 && chmod 644 /opt/halite/hlt.h

COPY halite_common.py /opt/halite/halite_common.py
COPY generate_round_traces.py /opt/halite/generate_round_traces.py
COPY generate_initial_traces_json.py /opt/halite/generate_initial_traces_json.py
COPY score_halite_submission.py /opt/halite/score_halite_submission.py
COPY halite_action_runner.py /opt/halite/halite_action_runner.py
COPY run_probe_impl.py /opt/halite/run_probe_impl.py
COPY run_probe /usr/local/bin/run_probe
RUN chmod 644 /opt/halite/*.py \
 && chmod 755 /usr/local/bin/run_probe \
 && echo "agent ALL=(root) NOPASSWD: /usr/local/bin/run_probe" > /etc/sudoers.d/probe \
 && chmod 440 /etc/sudoers.d/probe

COPY staging/target/ /target/
COPY staging/resolved_task.json /target/resolved_task.json
COPY staging/instruction.md /workspace/instruction.md
COPY staging/opponents/ /opt/revengebench/opponents/

RUN mkdir -p /workspace/submission /workspace/probe
COPY starter_main.c /workspace/submission/main.c
RUN cp /opt/halite/hlt.h /workspace/submission/hlt.h \
 && echo 25 > /workspace/.probe_budget \
 && chown root:root /workspace/.probe_budget \
 && chmod 644 /workspace/.probe_budget \
 && python3 -I /opt/halite/generate_round_traces.py \
 && python3 -I /opt/halite/generate_initial_traces_json.py \
 && find /workspace/rounds -name '_target_*' -delete \
 && cp -a /workspace/submission/. /workspace/probe/ \
 && chown -R root:root /target /opt/revengebench/opponents /workspace/rounds \
 && chmod 700 /target \
 && chmod 700 /opt/revengebench /opt/revengebench/opponents \
 && chmod -R go-rwx /opt/revengebench/opponents \
 && chmod -R a+rX /workspace/rounds \
 && chmod -R a-w /workspace/rounds \
 && chown -R agent:agent /workspace/submission /workspace/probe /workspace/instruction.md /logs

USER agent
