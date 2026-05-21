# Codex-enabled BattleSnake arena image.
#
# Layered on top of the base revenge_bench/battlesnake image:
# - installs Node.js + the `@openai/codex` CLI,
# - bakes in scripts/codex_exec.sh as
#   /usr/local/bin/revenge-codex-exec for the agent's wall-clock /
#   submit-marker watchdog wrapper.
#
# Build context is the repo root (see arena.py `_build_docker_image`),
# so the COPY path is repo-relative.
#
# Selected automatically by `arena._build_docker_image` when any player
# in the config has `agent: inverse_codex`. See the locked-decisions
# table in .cursor/plans/codex-integration_*.plan.md.

FROM revenge_bench/battlesnake

ENV DEBIAN_FRONTEND=noninteractive

# Node.js 20 (current LTS). Ubuntu 22.04's apt-side default is too old
# for recent codex CLI versions; pull from NodeSource instead.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && node --version && npm --version

# Codex CLI — pinned per .cursor/plans for reproducibility. Bump the
# version here when intentionally upgrading; the agent doesn't constrain
# it at runtime.
RUN npm install -g @openai/codex@latest \
 && codex --version

# Watchdog wrapper invoked by `CodexInverseStrategyAgent` instead of
# calling `codex exec` directly. Handles submit-marker → SIGTERM and
# wall-clock → 124 on top of whatever args the agent passes through.
COPY scripts/codex_exec.sh /usr/local/bin/revenge-codex-exec
RUN chmod +x /usr/local/bin/revenge-codex-exec

# CODEX_HOME defaults to ~/.codex; we intentionally use /codex_home
# (outside /workspace) so Player._commit() doesn't stage Codex caches.
# Pre-create the dir so the agent's first `mkdir -p` is a no-op.
RUN mkdir -p /codex_home

WORKDIR /workspace
