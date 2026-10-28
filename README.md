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

## v2: modal composer, live pages, hardening

- **Publish modal** from anywhere: sidebar "New post", the `c` key, empty queue slots, calendar days, idea cards and "Reuse" on sent posts open the composer in a dialog (a full-screen sheet on phones), prefilled from the context. `/compose` still works as a page.
- **Autosave and resume**: drafts are saved every 2 s while you type; reopening an empty composer offers to resume or discard the last one (hidden from the Posts and Queue lists).
- **Media**: drop or paste images into the composer, upload progress per file, drag thumbnails to reorder.
- **No reloads**: Queue, Calendar, Ideas, Inbox and the Overview update in place (HTMX partials + `HX-Trigger` events `toast`, `post-saved`, `posts-changed`); the Overview table and Inbox poll in the background.
- **Keyboard**: `c` new post, `g` + `o/q/c/i/p/n/a/s` to jump, `/` or `⌘K` command palette, `?` help.
- **Onboarding**: the Overview shows a five-step checklist (channel, brand voice, posting times, first post, Zernio key) until it is complete or dismissed (per user, `User.prefs`).
- **Hardening**: CSRF on every state-changing request, rate limits on login/setup and public link routes, security headers (CSP, nosniff, frame options), friendly 500 page, and a test that every write route requires a role.
- **CI**: `.github/workflows/ci.yml` runs ruff, pytest and a Playwright browser flow (`tests/e2e/`), then builds the Docker image. Locally: `uv run playwright install chromium` once, then `uv run pytest tests/e2e -o addopts=""`.

## Notifications, preferences and Zernio webhooks

- **Email notifications** (worker, every minute): editors and owners get one email when a post fails for good; owners get one per post waiting for approval. **Weekly digest** on Monday 07:00 UTC per brand: published count, impressions, engagements, link clicks, top posts, what is scheduled. Each user opts in or out under **Preferences** (`/me`), which also holds the composer's default action, keyboard shortcuts on/off and the password.
- **Zernio webhooks** replace polling for the moments that matter. On *Social accounts* an owner presses **Enable webhooks**; Spark registers `{SPARK_BASE_URL}/webhooks/zernio` with Zernio for post and account events. Deliveries are verified with HMAC-SHA256 (`X-Zernio-Signature`; secret from `SPARK_ZERNIO_WEBHOOK_SECRET`, or derived from `SPARK_SECRET_KEY`) and de-duplicated by event id. `post.platform.published/failed`, `post.published/failed/partial` update the matching post target; `account.disconnected` pauses the channel with the reason; `account.connected` adds the channel to the brand whose Zernio profile it belongs to.
