# RevengeBench RoboCode inverse-strategy task (Tier I, interactive).
#
# The target and sampled opponents are baked into the image but sealed
# root-only. The learner sees only visible round-0 traces and can query the
# sealed target through sudo run_probe.

FROM revenge_bench/robocode

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

RUN groupmod -n agent ubuntu \
 && usermod -l agent -d /home/agent -m ubuntu \
 && usermod -s /bin/bash agent

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
 && python3 -I -c "from revenge_bench.traces.parsers import robocode; print('revenge_bench RoboCode import OK')"

RUN mkdir -p /opt/robocode /opt/revengebench /target /logs/verifier /run

COPY generate_round_traces.py /opt/robocode/generate_round_traces.py
COPY generate_initial_traces_json.py /opt/robocode/generate_initial_traces_json.py
COPY score_robocode_submission.py /opt/robocode/score_robocode_submission.py
COPY robocode_learner_runner.py /opt/robocode/robocode_learner_runner.py
COPY run_probe_impl.py /opt/robocode/run_probe_impl.py
COPY run_probe /usr/local/bin/run_probe
RUN chmod 644 /opt/robocode/*.py \
 && chmod 755 /usr/local/bin/run_probe \
 && echo "agent ALL=(root) NOPASSWD: /usr/local/bin/run_probe" > /etc/sudoers.d/probe \
 && chmod 440 /etc/sudoers.d/probe

COPY staging/target/ /target/
COPY staging/resolved_task.json /target/resolved_task.json
COPY staging/instruction.md /workspace/instruction.md
COPY staging/opponents/ /opt/revengebench/opponents/

COPY starter_main.py /workspace/main.py
COPY starter_MyTank.java /workspace/robots/custom/MyTank.java

RUN echo 25 > /workspace/.probe_budget \
 && chown root:root /workspace/.probe_budget \
 && chmod 644 /workspace/.probe_budget \
 && javac -cp "libs/robocode.jar" /workspace/robots/custom/*.java \
 && python3 -I /opt/robocode/generate_round_traces.py \
 && python3 -I /opt/robocode/generate_initial_traces_json.py \
 && rm -rf /workspace/robots/p0 /workspace/robots/p1 \
 && rm -f /workspace/battles/harbor.battle /workspace/battles/probe.battle \
 && rm -f /workspace/robots/custom/*.class \
 && cp -r /workspace/robots/custom /workspace/probe \
 && chown -R root:root /target /opt/revengebench/opponents /workspace/rounds \
 && chmod 700 /target \
 && chmod 700 /opt/revengebench /opt/revengebench/opponents \
 && chmod -R go-rwx /opt/revengebench/opponents \
 && chmod -R a+rX /workspace/rounds \
 && chmod -R a-w /workspace/rounds \
 && chown -R agent:agent /workspace/main.py /workspace/robots/custom /workspace/probe /workspace/instruction.md /logs

RUN ln -sf /opt/java/openjdk/bin/java /usr/local/bin/java \
 && ln -sf /opt/java/openjdk/bin/javac /usr/local/bin/javac

USER agent
