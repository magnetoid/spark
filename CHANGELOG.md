# Changelog

Changes that matter to people who run Spark. Dates are when the change reached `main`.

## Unreleased

**Before you upgrade:** nothing to do. Optionally set `SPARK_SETUP_TOKEN` on new installs.

- A setup checklist on **Today** for owners: Zernio key, webhooks, channels, posting times,
  first post, email, public address, secret key, worker and two-factor, each with a link to fix
  it.
- `SPARK_SETUP_TOKEN`: when set, creating the first owner asks for it.
- New guides in `docs/`: install, configuration, connectors, upgrading and troubleshooting;
  a complete `.env.example` and a `docker-compose.example.yml` for any server.
- Fix: creating the first brand on a new install showed "Something went wrong" instead of
  Channels.

## 2026-11-14

- Channel health: Spark checks every channel each hour and tells the team once by email, chat
  and webhook when one needs reconnecting, or 7, 3 and 1 days before its access ends. New
  webhook events `channel.reconnect_needed`, `channel.expiring` and `channel.recovered`.
- Publishing health on the Sent and Failed views: success rate, failures by channel and
  reason, the next post per channel.
- A post retried after a timeout can no longer go out twice.
- Per-channel settings for Pinterest boards, Reddit subreddits, and TikTok and YouTube privacy.
- `/healthz` reports the database, Redis, when the worker last checked in, and the version.
- Fixes: inbox likes, discarding a prepared reply, PDF uploads, marking inbox items read at the
  network, drafts counted twice on Today, the link field not shortened, and the composer
  offering to resume the post being typed.
