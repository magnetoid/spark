# Contributing to Spark

Thank you for helping. Bug reports, fixes, docs and features are all welcome. For a larger
change, open an issue first so we can agree on the approach before you spend time on it.

## Set up

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22, and optionally Redis.

```bash
uv sync
(cd frontend && npm install)
printf 'SPARK_FORCE_DRY_RUN=true\n' > .env
uv run spark serve --reload                 # API and built app on http://localhost:8000
(cd frontend && npm run dev)                # the app with hot reload on http://localhost:5173
uv run spark worker                         # only when you work on publishing or background jobs
```

`SPARK_FORCE_DRY_RUN=true` makes every channel a test channel, so you can publish without real
accounts. SQLite is used unless you set `SPARK_DATABASE_URL`.

## Before you open a pull request

Run what CI runs:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q --ignore=tests/e2e
uv run python -m spark.api.openapi frontend/src/api/openapi.json && (cd frontend && npm run api:types)
(cd frontend && npm run typecheck && npm run lint && npm run test && npm run build)
uv run pytest -q tests/e2e                  # Playwright; run `uv run playwright install chromium` once
```

The OpenAPI step must leave no changes: commit the regenerated `openapi.json` and `schema.d.ts`
with any API change.

## How we work

- **Tests first.** A fix starts with a test that fails without it. API tests live in
  `tests/api/` and use the `api` (signed-in owner) and `anon` fixtures; outside HTTP calls are
  mocked with `respx`.
- **Migrations only add.** New columns are nullable or have a server default, written with
  `op.batch_alter_table` so they run on SQLite and PostgreSQL. Check both `upgrade` and
  `downgrade`.
- **Sensitive actions stay off by default.** Anything that sends private messages, spends money
  or publishes without a person's review needs a switch an owner turns on, and leaves an entry
  in the activity log.
- **Plain words in the interface.** Name things by what people do ("Reconnect", "Posting
  times"), not by how the code works. Error messages say what happened and how to fix it.
- Keep pull requests to one change. Describe what it changes for the people using Spark and how
  you checked it.

## Where things are

| Path | What |
|---|---|
| `src/spark/api/` | The JSON API under `/api/v1` (routes, schemas, dependencies) |
| `src/spark/services/` | The logic: publishing, inbox, analytics, AI, notifications |
| `src/spark/platforms/` | One adapter per provider (Zernio, Bluesky, Mastodon, Telegram, direct apps) |
| `src/spark/worker.py` | Background jobs and their schedule |
| `src/spark/mcp_server.py` | The MCP server |
| `frontend/src/` | The React app |
| `alembic/versions/` | Database migrations |
| `docs/` | Guides for people who install Spark |
