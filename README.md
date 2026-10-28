# Spark

Social autoposter and marketing app for a team or agency. Python/FastAPI, server-rendered.

- **Publish everywhere**: X, LinkedIn, Facebook Pages, Instagram, Threads, TikTok, YouTube, Pinterest, Bluesky, Mastodon, Telegram, Reddit and more. One post, per-platform text, media, live character gauges.
- **Zernio first**: set one `SPARK_ZERNIO_API_KEY` and connect any platform through [Zernio](https://docs.zernio.com) — no developer apps to register. Direct adapters (your own OAuth apps) are there too.
- **Queue-first, like Buffer**: per-channel Queue with visible posting slots, *Add to queue* / *Share next* (bumps the rest down) / *Share now* / pick a time, Drafts · Approvals · Sent tabs per channel.
- **Composer**: one text, per-channel customisation with live previews and character gauges, *first comment* (X, LinkedIn, Facebook, Instagram, Threads, YouTube, Bluesky, Mastodon), *Split into thread* for X / Threads / Bluesky / Mastodon.
- **Ideas board**: a kanban scratchpad (Ideas → Drafting → Ready → Done) with tags, AI drafting, and "Turn into post".
- **Inbox**: comments on your posts across Zernio-connected channels — read threads, reply, like — from one page.
- **Content library**: saved hashtag groups and post templates, one click away in the composer.
- **Scheduling**: queue slots per brand, month and week calendar with drag-to-reschedule and channel/campaign filters, approvals (editors submit, owners approve), retries with backoff, best-time suggestions.
- **AI**: Claude writes posts in your brand voice, adapts per platform, rewrites, suggests hashtags, plans whole campaigns, drafts emails.
- **Grow**: analytics per post/platform, UTM builder and click-tracked short links, RSS → posts, contacts and lists with CSV import, email campaigns with open/click tracking, a link-in-bio page with email capture and per-link click counts.
- **Multi-brand**: an agency runs every client in one install. Roles: owner / editor / viewer.

## Run it

```bash
cp .env.example .env     # set SPARK_SECRET_KEY, SPARK_BASE_URL, and the keys you have
docker compose up -d
```

Open http://localhost:8000 — the first visit asks you to create the owner account.

For a quick local look without Docker, Postgres or Redis:

```bash
uv sync
printf 'SPARK_FORCE_DRY_RUN=true\n' > .env
uv run spark serve --reload       # http://localhost:8000, SQLite, fake posting
uv run spark tick                 # publish due posts once (what the worker's cron does)
```

With `SPARK_FORCE_DRY_RUN=true` every platform connects with a fake account and posts are recorded locally, so the whole flow can be tried end to end.

## Processes

| Command | What it does |
|---|---|
| `spark serve` | Web app (uvicorn) |
| `spark worker` | ARQ worker: publishes due posts every 30s, retries, pulls metrics every 6h, polls RSS feeds, sends scheduled emails |
| `spark tick` | One publishing pass without Redis |
| `spark create-user EMAIL --role owner` | Add a user from the CLI |
| `alembic upgrade head` | Apply migrations (the Docker image runs this on start) |

## Connecting accounts

### Through Zernio (recommended)

1. Create an API key at zernio.com and set `SPARK_ZERNIO_API_KEY`.
2. Social accounts → *Connect through Zernio* → pick a platform. Spark creates one Zernio profile per brand, sends you through Zernio's OAuth, and saves the returned account.
3. *Import from Zernio* pulls accounts you connected in Zernio's own UI.

Publishing goes through `POST /v1/posts` with `publishNow`; Spark keeps its own schedule, approvals and calendar. Media is uploaded to Zernio storage via presigned URLs. Metrics come from `GET /v1/analytics?postId=`.

### Directly

Register a developer app per platform and put the client id/secret in `.env` (`SPARK_X_CLIENT_ID`, …). The redirect URI is `{SPARK_BASE_URL}/accounts/callback/<platform>`. Notes:

- **X**: posting needs a paid API tier. Scopes: tweet.read tweet.write users.read media.write offline.access.
- **Meta** (Facebook Pages + Instagram): Instagram must be a professional account linked to a Page. Instagram and Facebook fetch media by URL, so `SPARK_BASE_URL` must be publicly reachable.
- **TikTok / YouTube**: public posting needs app review; TikTok posts are `SELF_ONLY` until approved.
- **Bluesky, Mastodon, Telegram**: no app needed — connect with an app password / access token / bot token.

## Configuration

See [.env.example](.env.example). Everything is `SPARK_*`. Secrets (OAuth tokens) are encrypted at rest with `SPARK_SECRET_KEY`; changing it invalidates stored tokens.

## Deploying on Coolify

Create a *Docker Compose* resource pointing at this repo, paste `.env` values into the environment, set `SPARK_BASE_URL` to the public domain, and attach the domain to the `web` service on port 8000. The `media` volume must persist.

## Development

```bash
uv sync
uv run pytest
uv run ruff check src tests
```

Layout: `src/spark/platforms/` (one adapter per network + `zernio.py` provider + `dry_run.py`), `services/` (publisher, scheduler, ai, analytics, links, rss, email), `web/` (routers: posts, queue, ideas, accounts, marketing…), `templates/` (Jinja + HTMX + Alpine on [Basecoat](https://basecoatui.com)), `worker.py`.

Schema changes go through Alembic: `uv run alembic revision --autogenerate -m "..."`, then `uv run alembic upgrade head` (the Docker image runs this on start). A dev database created by `create_all` needs `uv run alembic stamp <initial revision>` once before upgrading.
