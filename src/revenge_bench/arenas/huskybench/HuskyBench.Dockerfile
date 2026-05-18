FROM python:3.10-slim

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

RUN apt update && apt install -y \
wget \
git \
build-essential \
unzip \
lsof \
&& rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/CodeClash-ai/HuskyBench.git /workspace \
    && cd /workspace \
    && git remote set-url origin https://github.com/CodeClash-ai/HuskyBench.git
WORKDIR /workspace

# eval7's setup.py imports Cython at build time but doesn't declare it
# in a pyproject.toml build-system, so pip's isolated build fails with
# "ModuleNotFoundError: No module named 'Cython'". Install Cython first
# and pass --no-build-isolation so eval7 can see it.
RUN pip install --no-cache-dir "cython<3"
RUN pip install --no-cache-dir --no-build-isolation -r engine/requirements.txt
RUN mkdir -p /workspace/engine/output
