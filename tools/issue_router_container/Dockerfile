# Reproducible worker image for the opt-in, board-backed router integration suite.
FROM rust:1-bookworm AS rust-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libssl-dev pkg-config ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY rust ./rust
RUN cargo build --release --manifest-path rust/Cargo.toml --bin kbs

FROM node:22-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates git openssh-client python3 python3-venv python3-pip \
      libssl3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=rust-builder /src/rust/target/release/kbs /usr/local/bin/kbs
COPY python /opt/kanbus/python
RUN python3 -m venv /opt/kanbus/venv \
    && /opt/kanbus/venv/bin/pip install --no-cache-dir /opt/kanbus/python \
    && npm install --global @openai/codex@0.149.0 \
    && npm cache clean --force \
    && python3 -c 'import json, pathlib, subprocess; catalog=json.loads(subprocess.check_output(["codex", "debug", "models"])); model=next(item for item in catalog["models"] if item["slug"] == "gpt-5.6-luna"); tiers=model.setdefault("service_tiers", []); tiers.append({"id": "flex", "name": "Flex", "description": "Flex Processing"}) if not any(tier.get("id") == "flex" for tier in tiers) else None; pathlib.Path("/opt/kanbus/codex-models.json").write_text(json.dumps(catalog), encoding="utf-8")'

ENV PATH="/opt/kanbus/venv/bin:${PATH}" \
    KANBUS_NO_DAEMON=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace
