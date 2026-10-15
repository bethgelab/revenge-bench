# RevengeBench HuskyBench inverse-strategy task (Tier I, interactive).
#
# The target and sampled opponents are baked into the image but sealed
# root-only. The learner sees only visible round-0 traces and can query the
# sealed target through sudo run_probe.

FROM revenge_bench/huskybench

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    curl ca-certificates jq sudo ripgrep lsof \
 && rm -rf /var/lib/apt/lists/*

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
RUN python3 -m pip install --ignore-requires-python --no-deps /tmp/wheels/revenge_bench-*.whl \
 && python3 -m pip install pyyaml tqdm zstandard \
 && rm -rf /tmp/wheels \
 && python3 -I -c "from revenge_bench.harbor.traces.parsers import huskybench; print('revenge_bench HuskyBench import OK')"

RUN mkdir -p /opt/huskybench /opt/revengebench /target /logs/verifier /run /app/output

COPY huskybench_common.py /opt/huskybench/huskybench_common.py
COPY prepare_sealed_players.py /opt/huskybench/prepare_sealed_players.py
COPY generate_round_traces.py /opt/huskybench/generate_round_traces.py
COPY generate_initial_traces_json.py /opt/huskybench/generate_initial_traces_json.py
COPY score_huskybench_submission.py /opt/huskybench/score_huskybench_submission.py
COPY huskybench_learner_runner.py /opt/huskybench/huskybench_learner_runner.py
COPY run_probe_impl.py /opt/huskybench/run_probe_impl.py
COPY run_probe /usr/local/bin/run_probe
RUN chmod 644 /opt/huskybench/*.py \
 && chmod 755 /usr/local/bin/run_probe \
 && echo "agent ALL=(root) NOPASSWD: /usr/local/bin/run_probe" > /etc/sudoers.d/probe \
 && chmod 440 /etc/sudoers.d/probe

COPY staging/target/ /target_src/
COPY staging/resolved_task.json /tmp/resolved_task.json
COPY staging/instruction.md /workspace/instruction.md
COPY staging/opponents/ /opt/revengebench/opponents_src/

RUN python3 -I /opt/huskybench/prepare_sealed_players.py \
      --target-source /target_src \
      --target-dest /target \
      --opponents-source /opt/revengebench/opponents_src \
      --opponents-dest /opt/revengebench/opponents \
 && cp /tmp/resolved_task.json /target/resolved_task.json \
 && rm -rf /target_src /opt/revengebench/opponents_src /tmp/resolved_task.json \
 && echo 25 > /workspace/.probe_budget \
 && chown root:root /workspace/.probe_budget \
 && chmod 644 /workspace/.probe_budget \
 && python3 -I /opt/huskybench/generate_round_traces.py \
 && python3 -I /opt/huskybench/generate_initial_traces_json.py \
 && rm -rf /app/output/* /workspace/output/* output/* /run/huskybench_probe \
 && mkdir -p /workspace/probe \
 && cp -a /workspace/client /workspace/probe/client \
 && chown -R root:root /target /opt/revengebench/opponents /workspace/rounds \
 && chmod 700 /target \
 && chmod 700 /opt/revengebench /opt/revengebench/opponents \
 && chmod -R go-rwx /opt/revengebench/opponents \
 && chmod -R a+rX /workspace/rounds \
 && chmod -R a-w /workspace/rounds \
 && chown -R agent:agent /workspace/client /workspace/probe /workspace/instruction.md /logs

WORKDIR /workspace
USER agent
