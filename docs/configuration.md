# Configuration

Spark reads its settings from environment variables that start with `SPARK_`, or from a `.env`
file in the working directory. Names are not case sensitive. [`.env.example`](../.env.example)
lists every one with a sensible starting value.

Settings marked **Connectors** can also be saved in the app under **Settings → Connectors** by
a workspace owner. A value saved there is encrypted with `SPARK_SECRET_KEY` and wins over the
environment, so you can start with an empty `.env` for those and fill them in from the browser.

## Core

| Setting | Default | What it does |
|---|---|---|
| `SPARK_ENV` | `development` | Set `production` on a real install: session cookies are then sent over HTTPS only (when `SPARK_BASE_URL` starts with `https`), and the database is built by migrations instead of on start. |
| `SPARK_BASE_URL` | `http://localhost:8000` | The public address people and networks reach Spark at, with `https://`. Links in emails, short links, webhook addresses and media URLs are built from it. Networks fetch your media from here, so it must be reachable from the internet. |
| `SPARK_SECRET_KEY` | a placeholder | Signs sessions and encrypts saved tokens and connector values. Use 32 or more random characters (`openssl rand -hex 32`). Changing it signs everyone out and makes saved connector values and channel tokens unreadable. |
| `SPARK_DATABASE_URL` | `sqlite+aiosqlite:///./spark.db` | PostgreSQL for real use: `postgresql+asyncpg://user:pass@host:5432/spark`. SQLite is fine for trying Spark out. |
| `SPARK_REDIS_URL` | `redis://localhost:6379/0` | The queue the worker takes jobs from. |
| `SPARK_MEDIA_DIR` | `./media` | Where uploaded images, videos and PDFs are kept. Back it up with the database. |
| `SPARK_MAX_UPLOAD_MB` | `50` | The largest file one upload may be. |
| `SPARK_SPA_DIR` | `frontend/dist` | The built web app. The Docker image sets this for you. |
| `SPARK_SPA_BASE` | `/` | The path the web app is served under. Leave it at `/`. |

## Security

| Setting | Default | What it does |
|---|---|---|
| `SPARK_SETUP_TOKEN` | empty | When set, creating the first owner account asks for this value. Set it on any install with a public address, so the first stranger to open it cannot become the owner. It is only used once; you can remove it after setup. |
| `SPARK_REQUIRE_TWO_FACTOR` | `false` | Everyone who signs in with a password must set up two-factor first. Owners usually switch this in **Settings → Brand & team** instead. |

## Publishing

| Setting | Default | What it does |
|---|---|---|
| `SPARK_ZERNIO_API_KEY` | empty | **Connectors.** Your Zernio key (`sk_…`). One key publishes to Instagram, Facebook, LinkedIn, TikTok, YouTube, X, Threads, Pinterest, Google Business, Reddit, Snapchat and more. |
| `SPARK_ZERNIO_BASE_URL` | `https://zernio.com/api/v1` | **Connectors.** Change only if Zernio tells you to. |
| `SPARK_ZERNIO_WEBHOOK_SECRET` | derived | The secret Zernio signs its webhooks with. Leave it empty: Spark derives one from `SPARK_SECRET_KEY` and registers the webhook itself when an owner presses **Enable webhooks** on the Zernio card in **Settings → Connectors**. |
| `SPARK_PUBLISH_MAX_ATTEMPTS` | `3` | How often a post is tried on one channel before it is marked failed. |
| `SPARK_METRICS_MAX_CALLS_PER_RUN` | `200` | The most requests one metrics run may send to the networks or Zernio. Posts younger than 48 hours are read every run, posts 2 to 7 days old once a day, and posts 7 to 30 days old every third day. |
| `SPARK_FORCE_DRY_RUN` | `false` | `true` publishes nothing: every channel acts like a test channel. Use it on a copy of a live install. |

Bluesky, Mastodon and Telegram need no outside account: connect them under **Channels** with
an app password, an access token or a bot token.

### Direct network apps (advanced)

Without Zernio, Spark can talk to some networks directly with your own developer app. You
register an app with each network, wait for its review, and keep up with its rule changes; most
people should use Zernio instead. The redirect address for each is
`{SPARK_BASE_URL}/accounts/callback/<platform>`. These are read from the environment only.

| Setting | Network |
|---|---|
| `SPARK_X_CLIENT_ID`, `SPARK_X_CLIENT_SECRET` | X |
| `SPARK_LINKEDIN_CLIENT_ID`, `SPARK_LINKEDIN_CLIENT_SECRET` | LinkedIn |
| `SPARK_META_APP_ID`, `SPARK_META_APP_SECRET` | Facebook Pages and Instagram |
| `SPARK_THREADS_APP_ID`, `SPARK_THREADS_APP_SECRET` | Threads |
| `SPARK_PINTEREST_CLIENT_ID`, `SPARK_PINTEREST_CLIENT_SECRET` | Pinterest |
| `SPARK_TIKTOK_CLIENT_KEY`, `SPARK_TIKTOK_CLIENT_SECRET` | TikTok |
| `SPARK_GOOGLE_CLIENT_ID`, `SPARK_GOOGLE_CLIENT_SECRET` | YouTube |

## AI writing (Claude)

| Setting | Default | What it does |
|---|---|---|
| `SPARK_ANTHROPIC_API_KEY` | empty | **Connectors.** Turns on writing help, replies, plans and reports. Without it Spark works, minus the AI buttons. |
| `SPARK_AI_MODEL` | `claude-opus-5-5` | **Connectors.** The model for writing. |
| `SPARK_AI_EFFORT` | `medium` | **Connectors.** `low`, `medium` or `high`: how long the model thinks. |
| `SPARK_AI_MODEL_FAST` | `claude-haiku-5-5` | The model for quick, cheap jobs such as sorting the inbox. |

## Images

| Setting | Default | What it does |
|---|---|---|
| `SPARK_OPENAI_API_KEY` | empty | **Connectors.** Turns on image generation in the composer. |
| `SPARK_IMAGE_MODEL` | `gpt-image-2.6-flare` | **Connectors.** The image model. A retired name falls back to the default. |

## The Janus agent

Janus plans weeks, drafts posts and writes reports in the background. The Compose files run it
next to Spark and wire it up for you; these settings are for running it elsewhere or tuning it.

| Setting | Default | What it does |
|---|---|---|
| `SPARK_JANUS_MANAGED` | `false` | `true` when Janus runs in the same Compose stack: Spark writes its configuration. |
| `SPARK_JANUS_BASE_URL` | empty | **Connectors.** Where Janus answers, for example `http://janus:8642`. |
| `SPARK_JANUS_API_KEY` | empty | **Connectors.** The key Janus was started with (`API_SERVER_KEY`). |
| `SPARK_JANUS_MODEL` | empty | **Connectors.** Empty means the same model as `SPARK_AI_MODEL`. |
| `SPARK_JANUS_EFFORT` | `medium` | **Connectors.** `low`, `medium` or `high`. |
| `SPARK_JANUS_APPROVALS` | `manual` | **Connectors.** Shell approvals; leave it on `manual`. |
| `SPARK_JANUS_SOUL` | empty | **Connectors.** Who Janus is inside Spark. Empty means the built-in text. |
| `SPARK_JANUS_EXTRA_YAML` | empty | **Connectors.** Extra Janus configuration merged over what Spark writes. |
| `SPARK_JANUS_UPDATE_WEBHOOK` | empty | **Connectors.** For a Janus running elsewhere: a deploy hook that rebuilds it. |
| `SPARK_JANUS_UPDATE_TOKEN` | empty | **Connectors.** The bearer token for that hook. |

## Email

| Setting | Default | What it does |
|---|---|---|
| `SPARK_EMAIL_BACKEND` | `console` | **Connectors.** `console` only writes emails to the log, `smtp` or `resend` sends them. Invitations, password resets and alerts need a real one. |
| `SPARK_EMAIL_FROM` | `Spark <noreply@example.com>` | **Connectors.** The sender. |
| `SPARK_SMTP_HOST` | `localhost` | **Connectors.** |
| `SPARK_SMTP_PORT` | `587` | **Connectors.** |
| `SPARK_SMTP_USER` | empty | **Connectors.** |
| `SPARK_SMTP_PASSWORD` | empty | **Connectors.** |
| `SPARK_SMTP_TLS` | `true` | **Connectors.** STARTTLS on the SMTP connection. |
| `SPARK_RESEND_API_KEY` | empty | **Connectors.** For the `resend` backend. |

## Chat notifications

Any one destination is enough. All of these are **Connectors** settings.

| Setting | Default | What it does |
|---|---|---|
| `SPARK_CHAT_SLACK_WEBHOOK` | empty | A Slack or Mattermost incoming webhook. |
| `SPARK_CHAT_DISCORD_WEBHOOK` | empty | A Discord channel webhook. |
| `SPARK_CHAT_TEAMS_WEBHOOK` | empty | A Teams Workflows "when a webhook request is received" address. |
| `SPARK_CHAT_TELEGRAM_TOKEN` | empty | A Telegram bot token. |
| `SPARK_CHAT_TELEGRAM_CHAT_ID` | empty | The chat the bot posts to. |
| `SPARK_CHAT_ON_APPROVAL` | `true` | Tell the chat when a post waits for approval. |
| `SPARK_CHAT_ON_FAILED` | `true` | … when a post fails. |
| `SPARK_CHAT_ON_REVIEW` | `true` | … when a new review arrives. |
| `SPARK_CHAT_ON_PUBLISHED` | `false` | … when a post goes out. |
| `SPARK_CHAT_ON_CHANNEL` | `true` | … when a channel needs reconnecting, is about to lose access, or works again. |
