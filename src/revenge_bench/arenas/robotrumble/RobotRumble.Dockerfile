# --platform=linux/amd64 pinned because the upstream RobotRumble repo ships a
# precompiled x86_64 `rumblebot` binary; without this, ARM64 hosts (Apple
# Silicon Macs) build an ARM64 image that lacks the x86_64 dynamic linker and
# cannot exec the binary even with Rosetta.
FROM --platform=linux/amd64 ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.10 (and alias python→python3.10), pip, and prerequisites
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    curl ca-certificates python3.10 python3.10-venv \
    python3-pip python-is-python3 wget git build-essential jq curl locales \
 && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/CodeClash-ai/RobotRumble.git /workspace \
    && cd /workspace \
    && git remote set-url origin https://github.com/CodeClash-ai/RobotRumble.git

WORKDIR /workspace
