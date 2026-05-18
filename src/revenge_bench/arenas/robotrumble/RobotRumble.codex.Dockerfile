# Codex-enabled RobotRumble arena image. See BattleSnake.codex.Dockerfile
# for design rationale; this file follows the identical pattern.
#
# Inherits the `linux/amd64` platform pin from the base image (FROM
# carries platform), which the upstream `rumblebot` binary requires.

FROM revenge_bench/robotrumble

ENV DEBIAN_FRONTEND=noninteractive

# The base RobotRumble image already has curl + ca-certificates.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && node --version && npm --version

RUN npm install -g @openai/codex@latest \
 && codex --version

COPY scripts/codex/inverse-codex-exec.sh /usr/local/bin/inverse-codex-exec
RUN chmod +x /usr/local/bin/inverse-codex-exec

RUN mkdir -p /codex_home

WORKDIR /workspace
