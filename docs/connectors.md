# Connectors

Connectors are the outside services Spark can use. A workspace owner sets them up under
**Settings → Connectors**; values saved there are encrypted and win over the environment
variables listed in [Configuration](configuration.md). Only the Zernio key matters for
publishing to the large networks; everything else is optional.

## Zernio (publishing)

[Zernio](https://docs.zernio.com) connects Instagram, Facebook, LinkedIn, TikTok, YouTube, X,
Threads, Pinterest, Google Business, Reddit, Snapchat and more with one API key. It is a paid
service with its own plans.

1. Create a key in Zernio (it starts with `sk_`) and paste it on the Zernio card.
2. Press **Enable webhooks** on the same card. Zernio then tells Spark right away when a post
   is published or fails, when a comment or message arrives, and when a channel is
   disconnected. Without webhooks Spark still learns all of this, only later, when its regular
   checks run.
3. Open **Channels** and press **Connect** for each network. You sign in at the network
   through Zernio; nothing has to be registered with the network yourself.

Some networks need a choice per channel: the Pinterest board, the Reddit subreddit, TikTok and
YouTube privacy. Set them with **Settings** on the channel's row.

Spark checks every Zernio channel each hour. When one needs reconnecting, or its access ends in
7, 3 or 1 days, the team is told once by email, chat and webhook, and the channel shows a badge
with a **Reconnect** button.

## Bluesky, Mastodon and Telegram (no outside account)

Connect these under **Channels → Connect directly**, without Zernio:

- **Bluesky**: your handle and an app password (Settings → App passwords in Bluesky).
- **Mastodon**: the server address and an access token with `write` permission (Preferences →
  Development → New application on your server).
- **Telegram**: a bot token from [@BotFather](https://t.me/BotFather) and the channel's @username or chat id; the bot
  must be an admin of that channel.

## Claude (AI writing)

An [Anthropic API key](https://console.anthropic.com) turns on writing and rewriting in the
brand's voice, hashtag and reply suggestions, campaign plans and report summaries. Pick the
model and effort on the same card. Usage is billed by Anthropic to your key.

## Image generation

An OpenAI API key turns on **Generate image** in the composer. Images are saved to the media
library like uploads.

## Janus (the agent)

Janus drafts a weekly plan from the brand's content pillars, voice and best times, and writes
reports. The Compose files run it next to Spark and connect it for you; it uses the Claude key.
Its card shows whether it answers and lets you tune its model, effort and personality. Janus
only drafts: a person approves before anything is scheduled.

## Email

Spark sends invitations, password resets, approval requests, failure and channel alerts, and
weekly digests. The default `console` backend only writes emails to the log. Pick **SMTP**
(any mail server or provider) or **Resend** (an API key) and send a test from the card.

## Chat notifications

Post alerts to Slack, Mattermost, Discord, Microsoft Teams or Telegram. Paste one incoming
webhook address (or a Telegram bot token and chat id) and choose what to be told about: posts
waiting for approval, failed posts, new reviews, published posts, and channels that need
attention.

## MCP access

Spark is an [MCP](https://modelcontextprotocol.io) server at `{SPARK_BASE_URL}/mcp`. Create a
personal token on the MCP card and add the server to Claude Code, Claude Desktop or any MCP
client. The assistant acts as you, with your role: it can list brands and channels, draft,
queue and schedule posts, add ideas and read analytics.

## Direct network apps (advanced)

Spark can also post through developer apps you register with X, LinkedIn, Meta, Threads,
Pinterest, TikTok or Google yourself. Each network reviews such apps and changes its rules
often, so this is for people who already have approved apps. The keys go in the environment
only; see [Configuration](configuration.md#direct-network-apps-advanced). The redirect address
to register is `{SPARK_BASE_URL}/accounts/callback/<platform>`.
