# Codex-enabled HuskyBench arena image. See BattleSnake.codex.Dockerfile
# for design rationale; this file follows the identical pattern with
# only the FROM line and curl install differing.

FROM revenge_bench/huskybench

ENV DEBIAN_FRONTEND=noninteractive

# python:3.10-slim base does not ship curl or ca-certificates; install
# them so the NodeSource bootstrap script can run.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && node --version && npm --version

RUN npm install -g @openai/codex@latest \
 && codex --version

COPY scripts/codex_exec.sh /usr/local/bin/revenge-codex-exec
RUN chmod +x /usr/local/bin/revenge-codex-exec

RUN mkdir -p /codex_home

WORKDIR /workspace
