# Janus next to Spark

Spark's agent is [Janus Agent](https://github.com/magnetoid/Janus-Agent), run as its own
service in the same Coolify project. Spark talks to it over HTTP (`POST /v1/runs`, SSE events,
approvals) and Janus reads Spark through Spark's MCP server with a read-only token. Janus
proposes; people approve in Spark. Nothing is scheduled or published by the agent itself.

## One-time setup in Coolify

1. **New application → Public repository** `https://github.com/magnetoid/Janus-Agent`, branch
   `main`, build pack **Docker Compose**, compose file `docker-compose.coolify.yml` (it is in
   the Janus repo). Name it `janus`.
2. **Environment variables** (Coolify → janus → Environment):

   | variable | value |
   |---|---|
   | `API_SERVER_ENABLED` | `true` |
   | `API_SERVER_HOST` | `0.0.0.0` |
   | `API_SERVER_PORT` | `8642` |
   | `API_SERVER_KEY` | a long random key (`openssl rand -hex 32`); Spark gets the same one |
   | `ANTHROPIC_API_KEY` | the Anthropic key |
   | `JANUS_GATEWAY_BOOTSTRAP_STATE` | `running` |
   | `SPARK_MCP_TOKEN` | a Spark API token (Settings → Preferences → MCP tokens) made for a user whose role on each brand is **viewer** |
   | `SPARK_MCP_URL` | `https://spark.imbamarketing.com/mcp` (or the internal `http://<spark service>:8000/mcp`) |

3. **Storage → file mount**: mount this folder's [`config.yaml`](config.yaml) at
   `/opt/data/config.yaml` and [`SOUL.md`](SOUL.md) at `/opt/data/SOUL.md` (Janus keeps its
   home in `/opt/data`). Paste the file contents; Coolify stores them as files.
4. **Networking**: no public domain is needed. Spark reaches Janus on the Coolify network as
   `http://janus:8642` (the compose service name). If Spark runs in another project, expose a
   domain with HTTPS and use that.
5. Deploy. `GET http://janus:8642/health` answers `{"status":"ok"}` once boot has finished.

## Tell Spark about it

Spark → Settings → Connectors → **Janus agent**: address `http://janus:8642`, API key = the
`API_SERVER_KEY` above. **Test** should report "healthy, version …". Optional: the Coolify
**deploy webhook** of the janus app (Coolify → janus → Webhooks; it looks like
`https://coo.imbamarketing.com/api/v1/deploy?uuid=<uuid>&force=true`) plus a Coolify API token
as the update token. With those, "Update now" in Spark rebuilds Janus from the latest `main`.

## Staying current

[`.github/workflows/janus-update.yml`](../../.github/workflows/janus-update.yml) calls the same
webhook every Monday at 05:00 UTC, so Janus follows its `main` branch weekly without anyone
remembering. Add two repository secrets: `COOLIFY_JANUS_WEBHOOK` (the webhook URL) and
`COOLIFY_TOKEN` (an API token). The "Update now" button in Spark does the same on demand.

## One Janus user per client, when it matters

The token Janus uses sees every brand its Spark user belongs to. For an agency whose clients
must never see each other's drafts through the agent, make one Spark user per brand (viewer on
that brand only), one token each, and one Janus service (or profile) per brand pointing at its
own token. A single shared viewer is fine when every brand belongs to the same team.

## What Janus is allowed to do

- Spark MCP tools are limited in `config.yaml` to reading: `list_brands`, `list_channels`,
  `list_posts`, `get_post`, `list_ideas`, `best_posting_times`, `get_analytics`. Writing tools
  are excluded, and the token's user is a viewer anyway.
- The `terminal` and code-execution toolsets are disabled; if Janus still asks to run a
  command, Spark answers **deny** automatically.
- Memory is per brand (Spark sends `X-Janus-Session-Key: spark-brand-<id>`), so what Janus
  learns about one client never leaks into another.
