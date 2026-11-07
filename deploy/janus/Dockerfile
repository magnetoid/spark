# Janus Agent (github.com/magnetoid/Janus-Agent) as Spark's built-in agent service.
# Built from the latest main; the layer below refreshes whenever main moves, so every Spark
# deploy ships the current Janus. At runtime run.sh pulls newer code on restarts too.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates && rm -rf /var/lib/apt/lists/*

ARG JANUS_REPO=https://github.com/magnetoid/Janus-Agent.git
ARG JANUS_REF=main
ENV JANUS_REPO=$JANUS_REPO JANUS_REF=$JANUS_REF
# cache-buster: GitHub's view of the branch head
ADD https://api.github.com/repos/magnetoid/Janus-Agent/commits/${JANUS_REF} /tmp/janus-head.json
RUN uv venv /opt/janus && uv pip install --python /opt/janus/bin/python \
    "janus-agent[messaging,mcp,anthropic] @ git+${JANUS_REPO}@${JANUS_REF}"

RUN useradd -m janus && mkdir -p /data/janus && chown -R janus:janus /data/janus /opt/janus
COPY deploy/janus/run.sh /usr/local/bin/janus-run
RUN chmod +x /usr/local/bin/janus-run
USER janus
ENV JANUS_HOME=/data/janus PATH="/opt/janus/bin:$PATH" \
    API_SERVER_ENABLED=true API_SERVER_HOST=0.0.0.0 API_SERVER_PORT=8642 \
    JANUS_GATEWAY_BOOTSTRAP_STATE=running JANUS_MAX_ITERATIONS=60 JANUS_AUTO_UPDATE=true
EXPOSE 8642
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s CMD curl -fsS http://127.0.0.1:8642/health || exit 1
CMD ["janus-run"]
