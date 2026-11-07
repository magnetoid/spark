# Janus, built in

Spark's agent is [Janus Agent](https://github.com/magnetoid/Janus-Agent). It runs as the
`janus` service of Spark's own `docker-compose.yml`, built by [`Dockerfile`](Dockerfile) from
the latest `main` of the Janus repository. **Nothing to configure**: compose generates one API
key (`SERVICE_PASSWORD_64_JANUSKEY`, created by Coolify like the other secrets) and gives it
to both sides, Spark knows the address (`http://janus:8642`), and on start Spark creates a
read-only agent account, an API token, and pushes Janus's whole configuration through Janus's
config API. Settings → Connectors → Janus shows the status and Janus's own options (model,
reasoning effort, personality, extra YAML for skills or more MCP servers); saving pushes them
again.

What Spark writes into Janus (see `services/janus_setup.py`):

- `mcp_servers.spark` → this Spark's `/mcp` with the agent token; only reading tools
  (`list_brands`, `list_channels`, `list_posts`, `get_post`, `list_ideas`,
  `best_posting_times`, `get_analytics`). The agent account is a viewer on every brand and
  can change nothing.
- `model` (Anthropic, Spark's model unless you pick another), `agent.reasoning_effort`,
  `agent.disabled_toolsets: [terminal, code_execution]`, `approvals.mode`, the `spark`
  personality (the text under "Personality"), and `ANTHROPIC_API_KEY` from Spark's Claude
  connector.
- Memory is per brand (`X-Janus-Session-Key: spark-brand-<id>` on every run).

Updates: [`run.sh`](run.sh) relaunches the gateway whenever it exits and, at most once an
hour, first pulls the latest Janus from the repository. "Update now" in Settings restarts it
for that reason, and Spark's worker does the same every Monday at 05:00 UTC. Every Spark
deploy also rebuilds the image from the current `main`.

## Running Janus elsewhere instead

Leave `SPARK_JANUS_MANAGED` unset, run Janus wherever you like with `API_SERVER_ENABLED=true`
and an `API_SERVER_KEY`, and enter its address and key under Settings → Connectors → Janus.
Spark then pushes the same configuration there. One Janus per client is the way to keep
agency clients apart: give each its own Spark agent user (viewer on that brand only).
