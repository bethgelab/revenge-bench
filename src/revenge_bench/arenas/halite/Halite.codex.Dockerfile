# Codex-enabled Halite arena image. See BattleSnake.codex.Dockerfile
# for design rationale; this file follows the identical pattern with
# only the FROM line changed.

FROM revenge_bench/halite

ENV DEBIAN_FRONTEND=noninteractive

# Node.js 20 (LTS) for the @openai/codex CLI. The base Halite image
# already has curl + ca-certificates, so we don't reinstall them.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && node --version && npm --version

RUN npm install -g @openai/codex@latest \
 && codex --version

COPY scripts/codex_exec.sh /usr/local/bin/revenge-codex-exec
RUN chmod +x /usr/local/bin/revenge-codex-exec

RUN mkdir -p /codex_home

WORKDIR /workspace
