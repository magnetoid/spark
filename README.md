# Spark

Spark is a self-hosted social media scheduler for a team or an agency. Plan, write, approve and
publish posts for several brands, answer comments and messages in one inbox, and show clients
what worked. It runs on your own server with Docker Compose.

Publishing goes through [Zernio](https://docs.zernio.com) by default: one API key reaches
Instagram, Facebook, LinkedIn, TikTok, YouTube, X, Threads, Pinterest, Google Business and more,
with no developer apps to register. Bluesky, Mastodon and Telegram work without any outside
account.

## What it does

**Publish without babysitting**
- A queue per channel with posting times, a month and week calendar with drag to reschedule,
  and *Share now*, *Share next* or a set time.
- One composer for every network: per-channel text, previews, first comment, threads, polls,
  Reels, Stories, carousels and LinkedIn documents.
- Retries with backoff and a stable idempotency key, so a post never goes out twice.
- Channel health: Spark notices a channel that needs reconnecting or whose access runs out,
  and tells the team once by email, chat or webhook.

**Less work per client**
- Many brands in one install, each with its own colour, voice, team and approval rules.
- Roles: owner, editor, viewer, and client (sees one brand, reads and approves).
- Review links that clients open without an account, comments on posts and an activity log.
- An inbox for comments, messages, reviews and mentions, with suggested replies, saved replies,
  assignment and rules that prepare a reply for approval.

**Growth and proof**
- Analytics per post, channel and period, follower history, and reports as CSV or a printable
  page with a written summary.
- Short links with click tracking, UTM tags per campaign, a link-in-bio page with email capture,
  RSS to posts, contacts and email campaigns.

**AI where it saves time (optional)**
- Claude writes and rewrites posts in the brand's voice, suggests hashtags and replies, and
  plans campaigns.
- Janus, a built-in agent, drafts a weekly plan from your content pillars and best times.
  Nothing is scheduled without a person's approval.
- An MCP server lets Claude and other AI assistants use Spark with a personal token.

## Quick start

You need Docker with Compose.

```bash
git clone https://github.com/magnetoid/spark.git && cd spark
cp .env.example .env
# Edit .env: SPARK_BASE_URL, SPARK_SETUP_TOKEN, and random values for
# SPARK_SECRET_KEY, POSTGRES_PASSWORD and SPARK_JANUS_API_KEY (openssl rand -hex 32)
docker compose -f docker-compose.example.yml up -d
```

Open the address you set in `SPARK_BASE_URL`, enter the setup token and create the owner
account. The checklist on **Today** walks through the rest: Zernio key, channels, posting times,
email and the background worker.

To try Spark without Docker, Postgres or Redis:

```bash
uv sync
(cd frontend && npm ci && npm run build)
printf 'SPARK_FORCE_DRY_RUN=true\n' > .env
uv run spark serve --reload       # http://localhost:8000 with SQLite and fake publishing
```

With `SPARK_FORCE_DRY_RUN=true` every channel connects with a fake account and posts are only
recorded, so the whole flow can be tried end to end.

## How publishing works

Spark keeps its own queue, calendar and approvals. When a post is due, the worker sends it to
the network through the channel's provider:

| Provider | Networks | What you need |
|---|---|---|
| Zernio (default) | Instagram, Facebook, LinkedIn, TikTok, YouTube, X, Threads, Pinterest, Google Business, Reddit, Snapchat, Bluesky, Mastodon, Telegram | A Zernio API key under **Settings → Connectors** |
| Built in | Bluesky, Mastodon, Telegram | An app password, access token or bot token |
| Your own apps (advanced) | X, LinkedIn, Meta, Threads, Pinterest, TikTok, YouTube | A developer app per network and its keys in the environment |

See [docs/connectors.md](docs/connectors.md) for each connector.

## Documentation

- [Install](docs/install.md): Docker Compose, a reverse proxy, Coolify, backups.
- [Configuration](docs/configuration.md): every `SPARK_*` setting.
- [Connectors](docs/connectors.md): Zernio, Claude, email, chat, images, Janus, MCP, direct apps.
- [Webhooks](docs/webhooks.md): events Spark sends to your own address.
- [Upgrading](docs/upgrading.md) and [Troubleshooting](docs/troubleshooting.md).

## Processes

| Command | What it does |
|---|---|
| `spark serve` | The web app and API |
| `spark worker` | Publishes due posts, retries, collects metrics, syncs the inbox and channels, sends emails and alerts |
| `spark tick` | One publishing pass without Redis |
| `spark create-user EMAIL --role owner` | Add a user from the command line |
| `spark reset-two-factor EMAIL` | Turn off two-factor for someone locked out |
| `alembic upgrade head` | Apply database migrations (the Docker image does this on start) |

## Development

```bash
uv sync
uv run pytest -q --ignore=tests/e2e
uv run ruff check src tests
cd frontend && npm install && npm run dev      # http://localhost:5173, proxies /api to :8000
```

The backend is FastAPI with SQLAlchemy and an ARQ worker (`src/spark/`). The JSON API lives at
`/api/v1` (`src/spark/api/`, OpenAPI at `/api/v1/openapi.json`). The interface is a React app in
`frontend/` built with Vite, TanStack Router and Query, and Tailwind. After an API change,
regenerate the client types:

```bash
uv run python -m spark.api.openapi frontend/src/api/openapi.json && (cd frontend && npm run api:types)
```

Database changes go through Alembic. See [CONTRIBUTING.md](CONTRIBUTING.md) for tests, style and
pull requests.

## Security

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## License

Not yet chosen. Until a license is added, the code is visible but no rights to use, copy or
modify it are granted.
